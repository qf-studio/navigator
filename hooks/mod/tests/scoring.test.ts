import { describe, expect, test } from 'claude-code/testing'

import { detectWorkflow, scoreAmbiguity } from '../lib/scoring'
import { SCORING_CASES } from './fixtures/scoring.gen'

describe('scoring parity with nav_hook_lib/scoring.py', () => {
  test('the corpus is not empty', () => {
    expect(SCORING_CASES.length).toBeGreaterThan(800)
  })
  test('detect_workflow matches on every corpus prompt', () => {
    const misses = SCORING_CASES.filter(c =>
      JSON.stringify(detectWorkflow(c.prompt)) !== JSON.stringify(c.workflow))
    expect(misses.map(c => c.prompt)).toEqual([])
  })
  test('score_ambiguity matches on every corpus prompt', () => {
    const misses = SCORING_CASES.filter(c =>
      JSON.stringify(scoreAmbiguity(c.prompt)) !== JSON.stringify(c.ambiguity))
    expect(misses.map(c => c.prompt)).toEqual([])
  })
})
