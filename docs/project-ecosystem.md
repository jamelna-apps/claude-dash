# Project Ecosystem & Dependencies

> **Last Updated:** January 2026
> **Auto-update:** This file should be reviewed when project relationships change

## Overview

This document maps the relationships between Joe's projects, their dependencies, and when to access each for different purposes.

---

## Project Groups

### GYST Ecosystem (Wardrobe/Fashion App)

The GYST app spans multiple repositories that work together:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GYST ECOSYSTEM                               │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────┐     ┌──────────────────┐                      │
│  │   WardrobeApp    │────▶│  ai-backend/     │                      │
│  │  (React Native)  │     │ (Node.js/Railway)│                      │
│  │                  │     └──────────────────┘                      │
│  │  iOS + Android   │                                               │
│  │  Main GYST App   │     ┌──────────────────┐                      │
│  └────────┬─────────┘────▶│  Firebase        │                      │
│           │               │  (Auth/Firestore)│                      │
│           │               └──────────────────┘                      │
│           │                                                         │
│           │               ┌──────────────────┐                      │
│           └──────────────▶│ gyst-seller-     │                      │
│                           │ portal (Next.js) │                      │
│                           │ gyst.store       │                      │
│                           └──────────────────┘                      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

| Project | Location | Purpose | Deployment |
|---------|----------|---------|------------|
| **WardrobeApp** | `/Projects/WardrobeApp` | Main mobile app (React Native/Expo) | App Store (iOS), Play Store (Android) |
| **ai-backend** | `/Projects/WardrobeApp/ai-backend` | AI API server | Railway (`gyst-ai-backend-production.up.railway.app`) |
| **gyst-seller-portal** | `/Projects/gyst-seller-portal` | Website + seller portal | Vercel (`gyst.store`) |

#### Shared Resources
- **Firebase Project:** Single shared Firebase for Auth + Firestore
- **RevenueCat:** Subscription management across mobile app
- **Claude AI:** Used by ai-backend for outfit suggestions, item detection

#### When to Edit What

| Task | Edit In |
|------|---------|
| App features, screens, navigation | `WardrobeApp/` |
| AI endpoints, outfit generation | `WardrobeApp/ai-backend/` |
| Public website (gyst.store) | `gyst-seller-portal/app/(marketing)/` |
| Seller portal dashboard | `gyst-seller-portal/app/(portal)/` |
| Privacy Policy / Terms of Service | `gyst-seller-portal/app/(marketing)/privacy/` and `terms/` |
| App Store metadata, screenshots | `WardrobeApp/docs/` |
| Firebase rules, indexes | `WardrobeApp/firestore.rules`, `firestore.indexes.json` |

---

### Jamelna Portfolio (Personal Website)

```
┌─────────────────────────────────────────────────────────────────────┐
│                       JAMELNA.COM                                    │
├─────────────────────────────────────────────────────────────────────┤
│  jamelna-site (Next.js)                                             │
│  ├── Portfolio showcase                                              │
│  ├── Work history (including GYST project description)              │
│  ├── Photography galleries (Sanity CMS)                             │
│  ├── Tech Sovereignty curriculum                                     │
│  └── K-12 CS Education resources                                     │
└─────────────────────────────────────────────────────────────────────┘
```

| Project | Location | Purpose | Deployment |
|---------|----------|---------|------------|
| **jamelna-site** | `/Projects/jamelna/jamelna-site` | Personal portfolio | Vercel (`jamelna.com`) |

#### Relationship to GYST
- jamelna.com **showcases** GYST as a portfolio project
- Different from gyst.store which is the **product website**
- Update jamelna when GYST features/description changes for portfolio purposes

---

### Other Projects

| Project | Location | Purpose | Deployment |
|---------|----------|---------|------------|
| **smartiegoals** | `/Projects/smartiegoals` | Goal tracking app | Vercel (`smartiegoals.org`) |
| **codetale** | `/Projects/codetale` | Kids coding education | Vercel (`codetale.jamelna.com`) |
| **spread-your-ashes** | `/Projects/spread-your-ashes` | Digital art project | Vercel (`spreadyourashes.com`) |
| **folio** | `/Projects/Folio` | TBD | — |
| **conductor** | `/Projects/conductor` | TBD | — |
| **AndroidGYST** | `/Projects/AndroidGYST` | Native Android GYST (experimental) | — |

---

## Quick Reference: Where to Find Things

### Legal/Compliance Documents

| Document | Location | URL |
|----------|----------|-----|
| GYST Privacy Policy | `gyst-seller-portal/app/(marketing)/privacy/` | `gyst.store/privacy` |
| GYST Terms of Service | `gyst-seller-portal/app/(marketing)/terms/` | `gyst.store/terms` |
| App Store Privacy Labels | `WardrobeApp/docs/APP_STORE_PRIVACY_LABELS.md` | — |

### Deployment Commands

| Project | Deploy Command |
|---------|----------------|
| WardrobeApp (iOS) | `cd WardrobeApp && npm run deploy` or `eas build --platform ios` |
| WardrobeApp (Android) | `cd WardrobeApp && npm run deploy:android` |
| gyst-seller-portal | `cd gyst-seller-portal && vercel --prod` or push to main |
| jamelna-site | `cd jamelna/jamelna-site && vercel --prod` or push to main |

### API Endpoints

| Service | URL | Source |
|---------|-----|--------|
| GYST AI Backend | `https://gyst-ai-backend-production.up.railway.app` | `WardrobeApp/ai-backend/` |
| GYST AI Health | `https://gyst-ai-backend-production.up.railway.app/health` | — |

---

## Decision Log: Project Splits

### Why gyst-seller-portal is separate from WardrobeApp

**Decision Date:** Late 2024

**Rationale:**
1. Web seller portal needs different tech stack (Next.js) than mobile app (React Native)
2. Public website (gyst.store) serves different audience than app users
3. Sellers need web dashboard for inventory management
4. Separation of concerns: mobile app vs web presence

**Shared:** Firebase project, Firestore collections, user authentication

### Why jamelna-site is separate from project sites

**Decision Date:** 2024

**Rationale:**
1. Portfolio site showcases ALL projects, not just one
2. Different update cadence (portfolio vs product)
3. Personal branding separate from product branding

---

## Maintenance Notes

### When to Update This Document

- [ ] New project added to ecosystem
- [ ] Project deployment location changes
- [ ] Dependencies between projects change
- [ ] New shared resources added
- [ ] Project archived or deprecated

### Files That Reference Project Relationships

- `/Users/jmelendez/.claude-dash/config.json` - Project registry
- `/Users/jmelendez/Documents/Projects/CLAUDE.md` - Projects directory instructions
- This file (`project-ecosystem.md`)

---

## Common Mistakes to Avoid

1. **Don't edit gyst.store content in WardrobeApp** - The website is in gyst-seller-portal
2. **Don't edit app features in gyst-seller-portal** - That's just the website
3. **Don't confuse jamelna.com GYST showcase with gyst.store** - Different purposes
4. **Privacy/Terms pages are on gyst.store**, not in the mobile app (app links to web)
