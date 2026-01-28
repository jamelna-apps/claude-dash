---
name: api-design
description: When the user mentions "API", "endpoint", "REST", "GraphQL", "route", "request", "response", "backend", or asks about designing web service interfaces.
---

# API Design Guide

## Design Principles

1. **Consistency** - Same patterns everywhere
2. **Predictability** - Clients can guess behavior
3. **Simplicity** - Easy to use correctly, hard to misuse
4. **Evolvability** - Can change without breaking clients

## REST API Design

### URL Structure
```
/resources                    # Collection
/resources/{id}               # Single resource
/resources/{id}/sub-resources # Nested resources
```

**Good:**
- `/users/123/orders`
- `/products?category=electronics`
- `/search?q=keyword`

**Bad:**
- `/getUser/123`
- `/users/123/getOrders`
- `/api/v1/fetch-all-products`

### HTTP Methods
| Method | Use Case | Idempotent |
|--------|----------|------------|
| GET | Read | Yes |
| POST | Create | No |
| PUT | Replace | Yes |
| PATCH | Partial update | Yes |
| DELETE | Remove | Yes |

### Status Codes
| Code | Meaning | When to Use |
|------|---------|-------------|
| 200 | OK | Successful GET, PUT, PATCH |
| 201 | Created | Successful POST |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Invalid input |
| 401 | Unauthorized | Not authenticated |
| 403 | Forbidden | Not authorized |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | State conflict (duplicate) |
| 422 | Unprocessable | Validation failed |
| 500 | Server Error | Unexpected error |

### Response Format
```json
{
  "data": { ... },
  "meta": {
    "page": 1,
    "total": 100
  }
}
```

Error response:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Email is required",
    "details": [
      { "field": "email", "message": "Required" }
    ]
  }
}
```

## Pagination

**Offset-based:**
```
/items?page=2&limit=20
```

**Cursor-based (preferred for large datasets):**
```
/items?cursor=abc123&limit=20
```

## Filtering & Sorting
```
/products?category=electronics&minPrice=100
/products?sort=price&order=desc
/products?fields=id,name,price
```

## Versioning Strategies

| Strategy | Example | Pros | Cons |
|----------|---------|------|------|
| URL path | `/v1/users` | Explicit, cacheable | URL pollution |
| Header | `Accept-Version: v1` | Clean URLs | Less visible |
| Query param | `?version=1` | Easy to test | Cache issues |

**Recommendation:** URL path versioning for simplicity.

## Authentication

| Method | Use Case |
|--------|----------|
| API Key | Server-to-server, simple |
| JWT | Stateless, distributed |
| OAuth 2.0 | Third-party access |
| Session | Traditional web apps |

## Rate Limiting

Include headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640000000
```

## Documentation Requirements

Every endpoint needs:
- URL and method
- Authentication required?
- Request parameters (path, query, body)
- Response format with examples
- Error codes and meanings
- Rate limits

## Common Mistakes

- Using verbs in URLs (`/getUsers`)
- Inconsistent naming (`/users` vs `/Users`)
- Returning 200 for errors
- No pagination on list endpoints
- Breaking changes without versioning
- Missing error details
- No rate limiting
