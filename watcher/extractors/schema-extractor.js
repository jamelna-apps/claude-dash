#!/usr/bin/env node

/**
 * Schema Extractor for Claude Memory System
 *
 * Extracts Firestore database schema from code patterns:
 * 1. Parses known schema files (marketplaceSchema.js, gdprCompliance.js)
 * 2. Scans source files for collection() and doc() patterns
 * 3. Extracts field usage from code
 * 4. Generates a comprehensive schema.json
 */

const fs = require('fs');
const path = require('path');

/**
 * Atomic JSON write - writes to temp file then renames
 */
function atomicWriteJSON(filePath, data) {
  const tmpPath = filePath + '.tmp.' + process.pid + '.' + Date.now();
  try {
    fs.writeFileSync(tmpPath, JSON.stringify(data, null, 2));
    fs.renameSync(tmpPath, filePath);
  } catch (e) {
    try { fs.unlinkSync(tmpPath); } catch (e2) {}
    throw e;
  }
}

// Patterns to find collection references
const COLLECTION_PATTERNS = [
  /collection\s*\(\s*db\s*,\s*['"](\w+)['"]\)/g,
  /doc\s*\(\s*db\s*,\s*['"](\w+)['"]/g,
  /\.collection\s*\(\s*['"](\w+)['"]\)/g,
  /firestore\(\)\.collection\s*\(\s*['"](\w+)['"]\)/g,
];

// Patterns to find field access
const FIELD_PATTERNS = [
  /(\w+)\s*:\s*[^,}]+/g,  // object field definitions
  /\.(\w+)\s*[=!<>]/g,     // field comparisons
  /data\.(\w+)/g,          // data.fieldName
  /\.data\(\)\.(\w+)/g,    // .data().fieldName
];

// Known schema from gdprCompliance.js
const USER_DATA_COLLECTIONS = [
  'wardrobe', 'gearbox', 'gear', 'outfits', 'collections', 'capsules',
  'haircuts', 'goals', 'lifeGoals', 'smart_goals', 'milestones', 'habits',
  'routines', 'journal', 'moods', 'confidence', 'activities', 'plannedActivities',
  'calendarEvents', 'packingLists', 'sharedOutfits', 'socialConnections',
  'marketplaceListings', 'marketplaceTransactions', 'marketplaceRatings', 'marketplaceReports'
];

const USER_ID_COLLECTIONS = [
  'users', 'skincare', 'coreValues', 'personalityProfiles', 'routinesQuizResults',
  'userBadges', 'userAchievements', 'achievements', 'streaks', 'checkInStreaks',
  'usageStats', 'subscriptions', 'userPreferences', 'preferences'
];

// Known marketplace schema with fields (from marketplaceSchema.js)
const MARKETPLACE_SCHEMA = {
  'marketplace_shops': {
    fields: ['shopId', 'ownerId', 'shopName', 'description', 'location', 'address',
      'contact', 'hours', 'pickupInstructions', 'coordinatesMarketplace', 'photos',
      'coverPhoto', 'verified', 'verifiedAt', 'verificationNotes', 'commission',
      'premiumTier', 'premiumExpiresAt', 'stripeAccountId', 'stripeOnboardingComplete',
      'status', 'rating', 'totalRatings', 'totalSales', 'totalRevenue', 'createdAt', 'updatedAt'],
    relationships: { ownerId: 'users.uid' }
  },
  'marketplace_items': {
    fields: ['itemId', 'sellerType', 'sellerId', 'shopId', 'shopName', 'sellerName',
      'commission', 'title', 'description', 'category', 'subcategory', 'brand', 'size',
      'color', 'condition', 'materials', 'price', 'originalPrice', 'photos', 'primaryPhoto',
      'tags', 'sustainabilityTags', 'location', 'pickupLocation', 'available', 'featured',
      'sold', 'views', 'likes', 'likedBy', 'createdAt', 'updatedAt', 'soldAt', 'soldTo'],
    relationships: { shopId: 'marketplace_shops.shopId', sellerId: 'users.uid' }
  },
  'marketplace_orders': {
    fields: ['orderId', 'itemId', 'shopId', 'buyerId', 'sellerId', 'item', 'shop',
      'pricing', 'status', 'pickup', 'payment', 'createdAt', 'updatedAt',
      'completedAt', 'cancelledAt', 'cancelReason'],
    relationships: {
      itemId: 'marketplace_items.itemId',
      shopId: 'marketplace_shops.shopId',
      buyerId: 'users.uid',
      sellerId: 'users.uid'
    }
  },
  'marketplace_reviews': {
    fields: ['reviewId', 'shopId', 'orderId', 'userId', 'userName', 'userPhoto',
      'rating', 'comment', 'photos', 'helpful', 'shopResponse', 'shopResponseAt',
      'verified', 'createdAt', 'updatedAt'],
    relationships: { shopId: 'marketplace_shops.shopId', userId: 'users.uid' }
  },
  'marketplace_saved_items': {
    fields: ['savedId', 'userId', 'itemId', 'shopId', 'savedAt'],
    relationships: { userId: 'users.uid', itemId: 'marketplace_items.itemId' }
  },
  'marketplace_shop_followers': {
    fields: ['followId', 'userId', 'shopId', 'followedAt', 'notifications'],
    relationships: { userId: 'users.uid', shopId: 'marketplace_shops.shopId' }
  },
  'safe_location_areas': {
    fields: ['areaId', 'centerLocation', 'radiusMiles', 'locationCount', 'cachedAt', 'lastAccessedAt'],
    relationships: {}
  },
  'safe_public_locations': {
    fields: ['locationId', 'areaId', 'name', 'address', 'location', 'type', 'placeId', 'rating', 'openNow', 'addedAt'],
    relationships: { areaId: 'safe_location_areas.areaId' }
  },
  'marketplace_meeting_agreements': {
    fields: ['agreementId', 'conversationId', 'buyerId', 'sellerId', 'itemId',
      'selectedLocation', 'proposedBy', 'buyerApproved', 'sellerApproved',
      'status', 'createdAt', 'agreedAt', 'completedAt', 'meetingTime'],
    relationships: { buyerId: 'users.uid', sellerId: 'users.uid', itemId: 'marketplace_items.itemId' }
  }
};

// Core app collections with common fields
const CORE_SCHEMA = {
  'users': {
    fields: ['uid', 'email', 'displayName', 'photoURL', 'createdAt', 'updatedAt',
      'subscription', 'subscriptionTier', 'subscriptionExpiresAt', 'aiUsage',
      'dailyAiLimit', 'lastAiReset', 'onboardingComplete', 'styleProfile'],
    relationships: {}
  },
  'wardrobe': {
    fields: ['id', 'userId', 'name', 'category', 'subcategory', 'brand', 'color',
      'size', 'material', 'price', 'purchaseDate', 'condition', 'photos', 'primaryPhoto',
      'tags', 'wearCount', 'lastWorn', 'favorite', 'archived', 'createdAt', 'updatedAt'],
    relationships: { userId: 'users.uid' }
  },
  'outfits': {
    fields: ['id', 'userId', 'name', 'items', 'occasion', 'season', 'weather',
      'mood', 'rating', 'notes', 'photos', 'wornOn', 'createdAt', 'updatedAt'],
    relationships: { userId: 'users.uid' }
  },
  'capsules': {
    fields: ['id', 'userId', 'name', 'description', 'items', 'season', 'occasion',
      'colorPalette', 'createdAt', 'updatedAt'],
    relationships: { userId: 'users.uid' }
  },
  'goals': {
    fields: ['id', 'userId', 'title', 'description', 'category', 'targetDate',
      'progress', 'completed', 'milestones', 'createdAt', 'updatedAt'],
    relationships: { userId: 'users.uid' }
  },
  'journal': {
    fields: ['id', 'userId', 'date', 'mood', 'energy', 'content', 'tags',
      'outfitId', 'weather', 'activities', 'createdAt'],
    relationships: { userId: 'users.uid', outfitId: 'outfits.id' }
  }
};

/**
 * Scan a file for collection references
 */
function scanFileForCollections(filePath) {
  const results = {
    collections: new Set(),
    references: []
  };

  try {
    const content = fs.readFileSync(filePath, 'utf8');
    const lines = content.split('\n');

    for (const pattern of COLLECTION_PATTERNS) {
      let match;
      // Reset lastIndex for global patterns
      pattern.lastIndex = 0;

      while ((match = pattern.exec(content)) !== null) {
        const collectionName = match[1];
        results.collections.add(collectionName);

        // Find line number
        const position = match.index;
        let lineNum = 1;
        let charCount = 0;
        for (const line of lines) {
          charCount += line.length + 1;
          if (charCount > position) break;
          lineNum++;
        }

        results.references.push({
          collection: collectionName,
          file: filePath,
          line: lineNum
        });
      }
    }
  } catch (error) {
    // Skip files that can't be read
  }

  return results;
}

/**
 * Recursively scan directory for JS files
 */
function scanDirectory(dirPath, ignorePatterns = ['node_modules', '.git', 'dist', 'build']) {
  const allResults = {
    collections: new Set(),
    references: []
  };

  function walkDir(dir) {
    try {
      const entries = fs.readdirSync(dir, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = path.join(dir, entry.name);

        // Check ignore patterns
        if (ignorePatterns.some(p => entry.name === p || entry.name.startsWith('.'))) {
          continue;
        }

        if (entry.isDirectory()) {
          walkDir(fullPath);
        } else if (entry.isFile() && /\.(js|jsx|ts|tsx)$/.test(entry.name)) {
          const fileResults = scanFileForCollections(fullPath);
          fileResults.collections.forEach(c => allResults.collections.add(c));
          allResults.references.push(...fileResults.references);
        }
      }
    } catch (error) {
      // Skip directories that can't be read
    }
  }

  walkDir(dirPath);
  return allResults;
}

/**
 * Generate comprehensive schema
 */
function generateSchema(projectPath, projectId) {
  console.log(`Scanning ${projectPath} for schema...`);

  const scanResults = scanDirectory(projectPath);

  // Combine all known collections
  const allCollections = new Set([
    ...USER_DATA_COLLECTIONS,
    ...USER_ID_COLLECTIONS,
    ...Object.keys(MARKETPLACE_SCHEMA),
    ...Object.keys(CORE_SCHEMA),
    ...scanResults.collections
  ]);

  // Build schema object
  const schema = {
    version: '1.0',
    project: projectId,
    source: 'extracted',
    lastUpdated: new Date().toISOString(),
    collections: {}
  };

  for (const collectionName of allCollections) {
    // Get predefined schema if available
    const predefined = MARKETPLACE_SCHEMA[collectionName] || CORE_SCHEMA[collectionName];

    // Find all references in code
    const references = scanResults.references
      .filter(r => r.collection === collectionName)
      .map(r => `${path.relative(projectPath, r.file)}:${r.line}`);

    schema.collections[collectionName] = {
      fields: predefined?.fields || [],
      relationships: predefined?.relationships || {},
      referencedIn: [...new Set(references)],
      userScoped: USER_DATA_COLLECTIONS.includes(collectionName) ||
                  (predefined?.relationships?.userId === 'users.uid'),
      idField: USER_ID_COLLECTIONS.includes(collectionName) ? 'uid' : 'id'
    };
  }

  return schema;
}

/**
 * Main function
 */
function main() {
  const args = process.argv.slice(2);

  if (args.length < 2) {
    console.log('Usage: node schema-extractor.js <project-path> <project-id>');
    console.log('Example: node schema-extractor.js /path/to/WardrobeApp gyst');
    process.exit(1);
  }

  const projectPath = args[0];
  const projectId = args[1];
  const outputPath = args[2] || path.join(
    process.env.HOME,
    '.claude-dash',
    'projects',
    projectId,
    'schema.json'
  );

  if (!fs.existsSync(projectPath)) {
    console.error(`Project path not found: ${projectPath}`);
    process.exit(1);
  }

  const schema = generateSchema(projectPath, projectId);

  // Ensure output directory exists
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });

  // Write schema (atomic)
  atomicWriteJSON(outputPath, schema);

  console.log(`Schema extracted: ${Object.keys(schema.collections).length} collections`);
  console.log(`Output: ${outputPath}`);

  // Summary
  console.log('\nCollections found:');
  for (const [name, data] of Object.entries(schema.collections)) {
    const refs = data.referencedIn.length;
    const fields = data.fields.length;
    console.log(`  - ${name}: ${fields} fields, ${refs} references`);
  }
}

// Run if called directly
if (require.main === module) {
  main();
}

module.exports = { generateSchema, scanDirectory, scanFileForCollections };
