# Contelligence RBAC Roles

This document describes the Azure AD app roles used by the Contelligence agent API.

## Role Definitions

| Role       | Value      | Description                                    |
|-----------|------------|------------------------------------------------|
| **Admin**    | `admin`    | Full access — session CRUD, admin endpoints, retention overrides |
| **Operator** | `operator` | Create/manage own sessions, view all outputs    |
| **Viewer**   | `viewer`   | Read-only access to sessions they own           |

## App Registration Setup

1. In Azure Portal → **Entra ID** → **App registrations** → your app.
2. Go to **App roles** and create the three roles above with `Value` matching the table.
3. Go to **Enterprise applications** → your app → **Users and groups**.
4. Assign users/groups to the appropriate roles.

## Permission Matrix

| Endpoint                           | Admin | Operator | Viewer | Unauthenticated (dev) |
|-----------------------------------|:-----:|:--------:|:------:|:---------------------:|
| `POST /api/agent/instruct`        | ✅    | ✅       | ❌     | ✅ (AUTH_ENABLED=false) |
| `GET  /api/agent/sessions`        | ✅ *  | ✅ **    | ✅ **  | ✅                     |
| `GET  /api/agent/sessions/{id}`   | ✅    | ✅ **    | ✅ **  | ✅                     |
| `DELETE /api/agent/sessions/{id}` | ✅    | ✅ **    | ❌     | ✅                     |
| `GET  /api/admin/cache/stats`     | ✅    | ❌       | ❌     | ✅                     |
| `POST /api/admin/cache/clear`     | ✅    | ❌       | ❌     | ✅                     |
| `GET  /api/admin/rate-limits`     | ✅    | ❌       | ❌     | ✅                     |

\* Admin sees all sessions  
\** Operator/Viewer see only their own sessions (filtered by `user_id = oid`)

## Session Isolation

- `SessionRecord.user_id` is set to the caller's `oid` at creation time.
- `list_sessions` filters by `user_id` for non-admin callers.
- Session access (GET/DELETE/stream) verifies ownership unless caller is admin.

## Environment Variables

| Variable              | Description                              | Default |
|----------------------|------------------------------------------|---------|
| `AUTH_ENABLED`       | Enable JWT validation                     | `false` |
| `AZURE_AD_TENANT_ID`| Azure AD tenant ID                        | —       |
| `AZURE_AD_CLIENT_ID`| App registration client (audience) ID     | —       |
