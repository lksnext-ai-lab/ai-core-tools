import React from 'react';

interface AuroraProps {
  colorStops?: string[];
  speed?: number;
  blend?: number;
  className?: string;
}

export const Aurora: React.FC<AuroraProps> = ({
  colorStops = ['var(--color-primary)', 'var(--color-secondary)', 'var(--color-accent)'],
  speed = 1,
  blend = 0.5,
  className = '',
}) => {
  return (
    <div className={`absolute inset-0 overflow-hidden ${className}`} aria-hidden="true">
      <style>{`
        @keyframes aurora-move {
          0%   { transform: translate(-20%, -20%) rotate(0deg) scale(1.2); }
          33%  { transform: translate(20%, -10%) rotate(120deg) scale(0.9); }
          66%  { transform: translate(-10%, 20%) rotate(240deg) scale(1.1); }
          100% { transform: translate(-20%, -20%) rotate(360deg) scale(1.2); }
        }
        @keyframes aurora-move-2 {
          0%   { transform: translate(20%, 20%) rotate(0deg) scale(1.1); }
          33%  { transform: translate(-20%, 10%) rotate(-120deg) scale(1.3); }
          66%  { transform: translate(10%, -20%) rotate(-240deg) scale(0.8); }
          100% { transform: translate(20%, 20%) rotate(-360deg) scale(1.1); }
        }
        @keyframes aurora-move-3 {
          0%   { transform: translate(0%, 20%) rotate(60deg) scale(1); }
          50%  { transform: translate(0%, -20%) rotate(180deg) scale(1.2); }
          100% { transform: translate(0%, 20%) rotate(300deg) scale(1); }
        }
      `}</style>
      {colorStops.map((color, i) => {
        const animationName = i === 0 ? 'aurora-move' : `aurora-move-${i + 1}`;
        return (
          <div
            key={`${color}-${i}`}
            style={{
              position: 'absolute',
              width: '80%',
              height: '80%',
              top: '10%',
              left: '10%',
              borderRadius: '50%',
              background: color,
              filter: 'blur(80px)',
              opacity: blend,
              animation: `${animationName} ${(8 + i * 3) / speed}s linear infinite`,
              mixBlendMode: 'screen',
            }}
          />
        );
      })}
    </div>
  );
};
