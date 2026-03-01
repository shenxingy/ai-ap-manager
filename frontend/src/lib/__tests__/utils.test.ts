import { cn } from '../utils';

describe('cn utility', () => {
  it('merges class names correctly', () => {
    const result = cn('px-4', 'py-2');
    expect(result).toContain('px-4');
    expect(result).toContain('py-2');
  });

  it('handles tailwind merge conflicts', () => {
    const result = cn('px-4 px-8');
    expect(result).toContain('px-8');
    expect(result).not.toContain('px-4 px-8');
  });

  it('handles array inputs', () => {
    const result = cn(['px-4', 'py-2']);
    expect(result).toContain('px-4');
    expect(result).toContain('py-2');
  });

  it('ignores falsy values', () => {
    const result = cn('px-4', false && 'py-2', undefined, null);
    expect(result).toContain('px-4');
  });

  it('returns empty string for no inputs', () => {
    const result = cn();
    expect(result).toBe('');
  });
});
