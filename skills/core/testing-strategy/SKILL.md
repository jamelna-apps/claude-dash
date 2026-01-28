---
name: testing-strategy
description: When the user mentions "test", "testing", "unit test", "integration", "e2e", "coverage", "TDD", "mock", or asks about testing approaches.
---

# Testing Strategy Guide

## Testing Pyramid

```
        /\
       /  \      E2E (Few)
      /----\
     /      \    Integration (Some)
    /--------\
   /          \  Unit (Many)
  /______________\
```

## Test Types

### Unit Tests
- **What:** Single function/component in isolation
- **Speed:** Fast (ms)
- **When:** Business logic, utilities, pure functions
- **Tools:** Jest, Vitest, pytest

### Integration Tests
- **What:** Multiple units working together
- **Speed:** Medium (seconds)
- **When:** API endpoints, database operations, component + hooks
- **Tools:** Supertest, Testing Library, pytest

### End-to-End Tests
- **What:** Full user flows
- **Speed:** Slow (10+ seconds)
- **When:** Critical paths, smoke tests
- **Tools:** Playwright, Cypress, Detox

## What to Test

### Always Test
- Business logic
- Edge cases (empty, null, boundary values)
- Error handling paths
- User-facing critical paths
- Security-sensitive operations

### Skip Testing
- Third-party library internals
- Trivial getters/setters
- Framework boilerplate
- Implementation details

## Test Structure (AAA Pattern)

```javascript
test('should calculate total with discount', () => {
  // Arrange - Set up test data
  const items = [{ price: 100 }, { price: 50 }];
  const discount = 0.1;

  // Act - Execute the code
  const total = calculateTotal(items, discount);

  // Assert - Verify the result
  expect(total).toBe(135);
});
```

## Naming Conventions

**Pattern:** `should [expected behavior] when [condition]`

Good:
- `should return empty array when no items match`
- `should throw error when user is not authenticated`
- `should redirect to login when session expires`

Bad:
- `test1`
- `works correctly`
- `calculateTotal`

## Mocking Guidelines

### When to Mock
- External services (APIs, databases)
- Time-dependent operations
- Random number generation
- File system operations

### When NOT to Mock
- The code under test
- Simple utilities
- When integration testing

### Mock Patterns
```javascript
// Partial mock
jest.mock('./api', () => ({
  ...jest.requireActual('./api'),
  fetchUser: jest.fn()
}));

// Reset between tests
beforeEach(() => {
  jest.clearAllMocks();
});
```

## React Testing

### Component Testing Library Pattern
```javascript
// Test behavior, not implementation
test('displays error when form is invalid', async () => {
  render(<SignupForm />);

  await userEvent.click(screen.getByRole('button', { name: /submit/i }));

  expect(screen.getByRole('alert')).toHaveTextContent(/email required/i);
});
```

### What to Query
```
getByRole > getByLabelText > getByPlaceholderText > getByText > getByTestId
```

## Coverage Guidelines

| Type | Target | Note |
|------|--------|------|
| Line | 80% | Minimum for CI gate |
| Branch | 70% | More important than line |
| Function | 90% | Ensure all exports tested |

**100% coverage is not a goal** - diminishing returns after ~85%

## Flaky Test Solutions

| Cause | Fix |
|-------|-----|
| Timing issues | Proper async/await, waitFor |
| Shared state | Reset in beforeEach |
| External dependencies | Mock them |
| Race conditions | Explicit ordering |
| Date/time | Mock Date.now() |

## Test Organization

```
src/
  components/
    Button/
      Button.tsx
      Button.test.tsx     # Co-located
  utils/
    format.ts
    format.test.ts
tests/
  integration/            # Cross-module tests
  e2e/                    # User flow tests
```

## CI/CD Integration

```yaml
# Run fast tests first
test:unit → test:integration → test:e2e
```

- Unit tests: Every commit
- Integration: Every PR
- E2E: Before deploy, nightly
