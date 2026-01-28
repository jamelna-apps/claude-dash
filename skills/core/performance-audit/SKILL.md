---
name: performance-audit
description: When the user mentions "slow", "performance", "optimize", "speed", "lag", "loading", "memory", "CPU", or asks to make something faster. Provides performance analysis framework.
---

# Performance Audit Framework

## Initial Assessment Questions

1. **What's slow?** - Page load, API response, build time, runtime
2. **How slow?** - Quantify: 3s vs 30s matters
3. **Baseline?** - What's acceptable performance?
4. **When?** - Always slow, or under certain conditions?
5. **Where?** - Client, server, network, database?

## Measurement First

**NEVER optimize without measuring.** Identify bottlenecks before fixing.

### Web Performance Metrics
- **LCP** (Largest Contentful Paint) - Main content visible
- **FID** (First Input Delay) - Interactivity
- **CLS** (Cumulative Layout Shift) - Visual stability
- **TTFB** (Time to First Byte) - Server response

### Tools
- Chrome DevTools Performance tab
- Lighthouse audit
- WebPageTest.org
- React DevTools Profiler
- `console.time()` / `console.timeEnd()`

## Common Performance Issues

### Frontend
| Issue | Detection | Fix |
|-------|-----------|-----|
| Large bundle | Webpack analyzer | Code splitting, tree shaking |
| Render blocking | Network waterfall | Defer/async scripts, critical CSS |
| Excessive re-renders | React Profiler | useMemo, useCallback, React.memo |
| Memory leak | Memory timeline | Cleanup effects, remove listeners |
| Layout thrashing | Performance timeline | Batch DOM reads/writes |

### Backend/API
| Issue | Detection | Fix |
|-------|-----------|-----|
| N+1 queries | Query logs | Eager loading, batching |
| Missing indexes | EXPLAIN plans | Add appropriate indexes |
| No caching | Repeated queries | Redis, in-memory cache |
| Sync blocking | Flame graphs | Async/await, worker threads |
| Large payloads | Network tab | Pagination, field selection |

### Database
| Issue | Detection | Fix |
|-------|-----------|-----|
| Full table scan | EXPLAIN | Add index on filter columns |
| Too many indexes | Write latency | Remove unused indexes |
| Large result sets | Memory usage | Pagination, streaming |
| Lock contention | Deadlock logs | Optimize transactions |

## Quick Wins Checklist

**Frontend:**
- [ ] Enable gzip/brotli compression
- [ ] Set cache headers
- [ ] Lazy load images and routes
- [ ] Use production builds
- [ ] Minimize third-party scripts

**Backend:**
- [ ] Add database indexes for common queries
- [ ] Implement response caching
- [ ] Use connection pooling
- [ ] Enable query result caching
- [ ] Optimize N+1 queries

## Performance Budget

Set limits and enforce:
- Bundle size: < 200KB (gzipped)
- API response: < 200ms (p95)
- Page load: < 3s (LCP)
- Build time: < 60s

## Output Format

When reporting:
1. **Current State** - Measured performance with numbers
2. **Bottlenecks** - Identified issues ranked by impact
3. **Recommendations** - Specific fixes with expected improvement
4. **Priority** - Quick wins vs larger refactors
