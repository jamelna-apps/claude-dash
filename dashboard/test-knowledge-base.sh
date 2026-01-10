#!/bin/bash
# Test script for Knowledge Base API endpoints

BASE_URL="http://localhost:3333"

echo "=== Testing Knowledge Base API Endpoints ==="
echo ""

echo "1. GET /api/knowledge-base - Get all sources"
curl -s "$BASE_URL/api/knowledge-base" | jq '.'
echo ""

echo "2. POST /api/knowledge-base - Add a URL (without Conductor)"
curl -s -X POST "$BASE_URL/api/knowledge-base" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://docs.example.com/api","title":"Example API Docs","tags":["api","docs"]}' | jq '.'
echo ""

echo "3. GET /api/knowledge-base - Verify source was added"
curl -s "$BASE_URL/api/knowledge-base" | jq '.'
echo ""

echo "4. DELETE /api/knowledge-base/:id - Remove the source"
SOURCE_ID=$(curl -s "$BASE_URL/api/knowledge-base" | jq -r '.sources[0].id')
if [ "$SOURCE_ID" != "null" ] && [ -n "$SOURCE_ID" ]; then
  echo "Deleting source: $SOURCE_ID"
  curl -s -X DELETE "$BASE_URL/api/knowledge-base/$SOURCE_ID" | jq '.'
  echo ""
  echo "5. GET /api/knowledge-base - Verify source was deleted"
  curl -s "$BASE_URL/api/knowledge-base" | jq '.'
else
  echo "No source to delete"
fi
echo ""

echo "=== Tests Complete ==="
