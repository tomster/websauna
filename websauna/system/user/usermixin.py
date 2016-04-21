"""Default user model field definitions.

This module defines what fields the default user implementation can have. You can subclass these mixins and then provide your own implementation for concrete models.
"""

from uuid import uuid4

import datetime
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import inspection, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Boolean
from sqlalchemy.orm.session import Session

from websauna.system.model.columns import UTCDateTime
from websauna.utils.crypt import generate_random_string
from websauna.utils.time import now
from websauna.utils.jsonb import JSONBProperty




#: Initialze user_data JSONB structure with these fields on new User
DEFAULT_USER_DATA = {
    "full_name": None,

    # The initial sign up method (email, phone no, imported, Facebook) for this user
    "registration_source": None,

    # Is it the first time this user is logging to our system? If it is then take the user to fill in the profile page.
    "first_login": True,

    "social": {
        # Each of the social media login data imported here as it goes through SocialLoginMapper.import_social_media_user()
    }
}


class UserMixin:
    """A user who signs up with email or with email from social media.

    This mixin provides the default required columns for user model in Websauna.

    The user contains normal columns and then ``user_data`` JSON field where properties and non-structured data can be easily added without migrations. This is especially handy to store incoming OAuth fields from social networks. Think Facebook login data and user details.
    """

    #: Running counter id of the user
    id = Column(Integer, autoincrement=True, primary_key=True)

    #: Publicly exposable ID of the user
    uuid = Column(UUID(as_uuid=True), default=uuid4)

    #: Though not displayed on the site, the concept of "username" is still preversed. If the site needs to have username (think Instragram, Twitter) the user is free to choose this username after the sign up. Username is null until the initial user activation is completed after db.flush() in create_activation().
    username = Column(String(256), nullable=True, unique=True)

    email = Column(String(256), nullable=True, unique=True)

    #: Stores the password + hash + cycles as password hasher internal format.. By default uses Argon 2 format. See :py:meth:`websauna.system.Initializer.configure_password`
    hashed_password = Column('password', String(256), nullable=True)

    #: When this account was created
    created_at = Column(UTCDateTime, default=now)

    #: When the account data was updated last time
    updated_at = Column(UTCDateTime, onupdate=now)

    #: When this user was activated: email confirmed or first social login
    activated_at = Column(UTCDateTime, nullable=True)

    #: Is this user account enabled. The support can disable the user account in the case of suspected malicious activity.
    enabled = Column(Boolean, default=True)

    #: When this user accessed the system last time. None if the user has never logged in (only activation email sent). Information stored for the security audits.
    last_login_at = Column(UTCDateTime, nullable=True)

    #: From which IP address did this user log in from. If this IP is null the user has never logged in (only activation email sent). Information stored for the security audits. It is also useful for identifying the source country of users e.g. for localized versions.
    last_login_ip = Column(INET, nullable=True)

    #: Misc. user data as a bag of JSON. Do not access directly, but use JSONBProperties below
    user_data = Column(JSONB, default=DEFAULT_USER_DATA)

    #: Store when this user changed the password or authentication details. Updating this value causes the system to drop all sessions which were created before this moment. E.g. you will kick out all old sessions on a password or email change.
    last_auth_sensitive_operation_at = Column(UTCDateTime, nullable=True, default=now)

    #: Full name of the user (if given)
    full_name = JSONBProperty("user_data", "/full_name")

    #: How this user signed up to the site. May include string like "email", "facebook" or "dummy". Up to the application to use this field. Default social media logins and email sign up set this.
    registration_source = JSONBProperty("user_data", "/registration_source", graceful=None)

    #: Social media data of the user as a dict keyed by user media
    social = JSONBProperty("user_data", "/social")

    #: Is this the first login the user manages to do to our system. If this flag is set the user has not logged in to the system before and you can give warm welcoming experience.
    first_login = JSONBProperty("user_data", "/first_login")

    @property
    def friendly_name(self):
        """How we present the user's name to the user itself.

        Picks one of 1) full name if set 2) username if set 3) email.
        """
        full_name = self.full_name
        if full_name:
            return full_name

        # Get the username if it looks like non-automatic form
        if self.username:
            if self.username.startswith("user-"):
                return self.email
            else:
                return self.username

        return self.email

    def generate_username(self):
        """The default username we give for the user."""
        assert self.id
        return "user-{}".format(self.id)

    def is_activated(self):
        """Has the user completed the email activation."""
        return self.activated_at is not None

    def can_login(self):
        """Is this user allowed to login."""
        # TODO: is_active defined in Horus
        return self.enabled and self.is_activated

    def is_in_group(self, name):

        # TODO: groups - defined in Horus
        for g in self.groups:
            if g.name == name:
                return True
        return False

    def is_admin(self):
        """Does this user the see the main admin interface link.

        TODO: This is very suboptimal, wasted database cycles, etc. Change this.
        """
        return self.is_in_group(GroupMixin.DEFAULT_ADMIN_GROUP_NAME)

    def is_valid_session(self, session_created_at:datetime.datetime) -> bool:
        """Check if the current session is still valid for this user."""
        return self.last_auth_sensitive_operation_at <= session_created_at

    def __str__(self):
        return self.friendly_name

    def __repr__(self):
        return "#{}: {}".format(self.id, self.friendly_name)


class GroupMixin:
    """Basic fields for Websauna default group model."""

    #: Assign the first user initially to this group
    DEFAULT_ADMIN_GROUP_NAME = "admin"

    #: Running counter id of the group
    id = Column(Integer, autoincrement=True, primary_key=True)

    #: Publicly exposable ID of the group
    uuid = Column(UUID(as_uuid=True), default=uuid4)

    #: Human readable / machine referrable name of the group
    name = Column(String(64), unique=True)

    #: Human readable description of the group
    description = Column(String(256))

    #: When this group was created.
    created_at = Column(UTCDateTime, default=now)

    #: When the group was updated last time. Please note that this does not concern group membership, only desription updates.
    updated_at = Column(UTCDateTime, onupdate=now)

    #: Extra JSON data to be stored with this group
    group_data = Column(JSONB, default=dict)


class SiteCreator:
    """Component responsible for setting up an empty site on first login.

    The site creator is run by the activation of the first user. This either happens¨

    * When the activation email is sent to the first user

    * When the first user logs through social media account

    """

    def init_empty_site(self, dbsession:Session, user:UserMixin):
        """When the first user signs up build the admin groups and make the user member of it.

        Make the first member of the site to be admin and superuser.
        """

        # Try to reflect related group class based on User model
        i = inspection.inspect(user.__class__)
        Group = i.relationships["groups"].mapper.entity

        # Do we already have any groups... if we do we probably don'¨t want to init again
        if dbsession.query(Group).count() > 0:
            return

        g = Group(name=Group.DEFAULT_ADMIN_GROUP_NAME)
        dbsession.add(g)

        g.users.append(user)

    def check_empty_site_init(self, dbsession:Session, user:UserMixin):
        """Call after user creation to see if this user is the first user and should get initial admin rights."""

        assert user.id, "Please flush your db"

        # Try to reflect related group class based on User model
        i = inspection.inspect(user.__class__)
        Group = i.relationships["groups"].mapper.entity

        # If we already have groups admin group must be there
        if dbsession.query(Group).count() > 0:
            return

        self.init_empty_site(dbsession, user)


class ActivationMixin:
    """Sign up / forgot password activation code reference."""

    #: Running counter id
    id = Column(Integer, autoincrement=True, primary_key=True)

    #: When this group was created.
    created_at = Column(UTCDateTime, default=now)

    #: When the group was updated last time. Please note that this does not concern group membership, only desription updates.
    updated_at = Column(UTCDateTime, onupdate=now)

    #: All activation tokens must have expiring time
    expires_at = Column(UTCDateTime, nullable=False)

    code = Column(String(32), nullable=False,
                         unique=True,
                         default=lambda: generate_random_string(32))

    def is_expired(self):
        """The activation best before is past and we should not use it anymore."""
        return self.expires_at < now()


class UserGroupMixin:
    """Map users to groups."""
    id = Column(Integer, autoincrement=True, primary_key=True)