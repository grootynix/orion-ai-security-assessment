# Authentication and Authorization

## Authentication

Tokens are HS256 JWTs issued by `TokenService`.

Required claims: `sub`, `iss`, `aud`, `exp`, `nbf`, `iat`, `jti`.

Unexpected algorithms, including `none`, are rejected.

After signature verification, Orion loads the canonical identity from `IdentityDirectory` and ignores any role/project claims present in the token payload.

### Development identity provider

`POST /api/token` exists only when:

- `ORION_ENV` is `development` or `test`
- `ORION_ENABLE_DEV_IDP=true`

Production refuses DevIdP enablement and requires `ORION_TOKEN_SIGNING_KEY`.

### Enterprise OIDC

`OidcIdentityProvider` is a fail-closed stub. Production identity federation requires JWKS, issuer, and audience configuration against an external IdP.

## Authorization

`AuthorizationService` is deny-by-default and is used by API routes and tool implementations.

| Resource | Rule |
| --- | --- |
| Public documents | All authenticated users |
| Project documents | Project membership or manager+ |
| Management documents | Manager+ |
| Customers | Assignee or manager+ |
| Send email | Manager+ and allowlisted recipient |
| Audit / outbox | Administrator |
| Approvals | Manager+ |

Object-level authorization is enforced for customer records using `assigned_to`.
