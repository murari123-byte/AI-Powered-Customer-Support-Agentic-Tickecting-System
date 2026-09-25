"""The four user roles, and the groups the code checks against.

Every user has exactly ONE role. Endpoints say which roles may call them, for example
`Depends(require_roles(*STAFF))`. That's the whole access-control system (RBAC).
"""

from enum import StrEnum


class Role(StrEnum):
    CUSTOMER = "CUSTOMER"
    SUPPORT_AGENT = "SUPPORT_AGENT"
    SUPPORT_MANAGER = "SUPPORT_MANAGER"
    ADMIN = "ADMIN"


# Everyone who works on tickets.
STAFF = frozenset({Role.SUPPORT_AGENT, Role.SUPPORT_MANAGER, Role.ADMIN})
# Can see every ticket, assign to anyone, and take tickets out of ESCALATED.
MANAGERS = frozenset({Role.SUPPORT_MANAGER, Role.ADMIN})
