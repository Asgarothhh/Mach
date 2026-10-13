import type { CSSProperties } from 'react';

const BAR_HEIGHTS = [16, 24, 18, 32, 40, 25, 48, 64, 34, 76, 52, 94, 70, 112, 84, 136, 102, 154, 118, 170, 132, 184, 142, 166, 126, 182, 144, 158, 112, 136, 92, 116, 72, 88, 54, 68, 38, 48, 27, 33, 18];

export function Waveform({ variant = 'hero', animated = false }: { variant?: 'hero' | 'stage' | 'mini'; animated?: boolean }) {
  return (
    <div className={`waveform waveform--${variant} ${animated ? 'waveform--animated' : ''}`} role="img" aria-label={animated ? 'Звуковая волна активна' : 'Звуковая волна'}>
      {BAR_HEIGHTS.map((height, index) => (
        <span key={`${height}-${index}`} style={{ '--bar-height': `${variant === 'mini' ? Math.max(6, height * 0.36) : variant === 'stage' ? height * 0.78 : height}px`, '--bar-index': index } as CSSProperties} />
      ))}
    </div>
  );
}
