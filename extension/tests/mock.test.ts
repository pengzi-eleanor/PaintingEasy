import { describe, expect, it } from 'vitest'
import { mockOptimize } from '../src/mock'

describe('mockOptimize', () => {
  it('为空输入返回空建议', () => expect(mockOptimize('  ')).toEqual([]))
  it('保留未匹配的原始查询并去重', () => {
    const result = mockOptimize('水彩森林')
    expect(result[0]).toMatchObject({ keyword: '水彩森林', selected: true })
    expect(new Set(result.map((item) => item.keyword)).size).toBe(result.length)
  })
  it('为中文场景词生成英文建议', () => {
    expect(mockOptimize('暖色咖啡海报').map((item) => item.keyword)).toContain('coffee')
  })
})
