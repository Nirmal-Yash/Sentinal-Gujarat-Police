import assert from 'node:assert/strict'
import { normalizePath } from '../dashboard/src/routeState.mjs'

const cases = new Map([
  ['/','/feeds'],
  ['/dashboard','/feeds'],
  ['/feeds','/feeds'],
  ['/map','/map'],
  ['/alerts','/alerts'],
  ['/investigations','/investigations'],
  ['/test','/test'],
  ['/does-not-exist','/feeds'],
])
for (const [input, expected] of cases) assert.equal(normalizePath(input), expected)
console.log(`route-state regression: ${cases.size}/${cases.size} passed`)
