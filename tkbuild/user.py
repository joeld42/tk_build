from enum import Enum
import logging
import datetime

class UserRole( str, Enum ):
    GUEST = 'guest'
    TESTER = 'tester'
    ADMIN = 'admin'

def validateRole( authUser, targetRole ):

    # User MUST have a custom claim since we
    # don't validate GUEST roles
    if not authUser or not authUser.get( 'role', None):
        return False

    # Check that the user role is at least as privledged as the target
    userRole = authUser.get('role', UserRole.GUEST )
    if userRole == UserRole.ADMIN:
        # Admin can do anything
        return True
    elif userRole == UserRole.TESTER:
        if targetRole == UserRole.TESTER:
            return True

    # Not enough permissions
    return False

# For now this doesn't have any data beyond whats
# in the Firebase Auth UserRecord
class TKBuildUser( object ):

    def __init__(self, authUser ):

        self.authUser = authUser

    def getRole(self):
        if (not self.authUser) or (self.authUser.custom_claims == None):
            return UserRole.GUEST
        else:
            return self.authUser.custom_claims.get('role', UserRole.GUEST )

    def getRoleName(self):
        return self.getRole().capitalize()

