import { useRef, useEffect, useState, useCallback } from 'react';

interface AIRobot3DProps {
  primaryColor?: string;
  accentColor?: string;
  className?: string;
  isSpeaking?: boolean;
  disableParallax?: boolean;
}

/**
 * Stylized AI robot head with 3D mouse-tracking parallax.
 * Designed for LIGHT backgrounds — uses dark fills with colored accents.
 * Accepts `isSpeaking` to animate the mouth faster (talking effect).
 * Pure SVG + CSS transforms — zero extra dependencies.
 */
const AIRobot3D: React.FC<AIRobot3DProps> = ({
  primaryColor = 'var(--color-primary)',
  accentColor = 'var(--color-accent)',
  className = '',
  isSpeaking = false,
  disableParallax = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tilt, setTilt] = useState({ x: 0, y: 0 });
  const frameRef = useRef<number>(0);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!containerRef.current) return;
    cancelAnimationFrame(frameRef.current);
    frameRef.current = requestAnimationFrame(() => {
      const rect = containerRef.current!.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const x = ((e.clientY - cy) / (rect.height / 2)) * -12;
      const y = ((e.clientX - cx) / (rect.width / 2)) * 12;
      setTilt({ x: Math.max(-15, Math.min(15, x)), y: Math.max(-15, Math.min(15, y)) });
    });
  }, []);

  const handleMouseLeave = useCallback(() => {
    setTilt({ x: 0, y: 0 });
  }, []);

  useEffect(() => {
    if (disableParallax) return;
    const el = document as unknown as HTMLElement;
    el.addEventListener('mousemove', handleMouseMove);
    el.addEventListener('mouseleave', handleMouseLeave);
    return () => {
      el.removeEventListener('mousemove', handleMouseMove);
      el.removeEventListener('mouseleave', handleMouseLeave);
      cancelAnimationFrame(frameRef.current);
    };
  }, [handleMouseMove, handleMouseLeave, disableParallax]);

  const mouthDur = isSpeaking ? '0.3s' : '1.5s';
  const mouthValues = isSpeaking ? '0.3;1;0.3' : '0.4;0.8;0.4';

  return (
    <div
      ref={containerRef}
      className={`flex items-center justify-center ${className}`}
      style={{ perspective: '800px' }}
    >
      <div
        style={{
          transform: `rotateX(${tilt.x}deg) rotateY(${tilt.y}deg)`,
          transition: 'transform 0.15s ease-out',
          transformStyle: 'preserve-3d',
        }}
      >
        <svg
          viewBox="0 0 200 220"
          className="w-full h-full"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          style={{ filter: 'drop-shadow(0 8px 24px rgba(0,0,0,0.12))' }}
        >
          <defs>
            <filter id="robotGlow" x="-30%" y="-30%" width="160%" height="160%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <linearGradient id="robotBodyGrad" x1="50%" y1="0%" x2="50%" y2="100%">
              <stop offset="0%" stopColor="#e2e8f0" />
              <stop offset="100%" stopColor="#cbd5e1" />
            </linearGradient>
            <linearGradient id="robotVisorGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" style={{ stopColor: primaryColor }} stopOpacity="0.9" />
              <stop offset="100%" style={{ stopColor: accentColor }} stopOpacity="0.7" />
            </linearGradient>
            <linearGradient id="robotHeadGrad" x1="50%" y1="0%" x2="50%" y2="100%">
              <stop offset="0%" stopColor="#f1f5f9" />
              <stop offset="100%" stopColor="#e2e8f0" />
            </linearGradient>
          </defs>

          {/* Antenna */}
          <line x1="100" y1="30" x2="100" y2="8" stroke="#94a3b8" strokeWidth="2.5" strokeLinecap="round" />
          <circle cx="100" cy="6" r="4" fill={primaryColor} filter="url(#robotGlow)">
            <animate attributeName="opacity" values="0.5;1;0.5" dur="2s" repeatCount="indefinite" />
          </circle>

          {/* Head */}
          <rect x="35" y="30" width="130" height="105" rx="28" ry="28" fill="url(#robotHeadGrad)" stroke="#cbd5e1" strokeWidth="1.5" />

          {/* Visor / face screen */}
          <rect x="50" y="50" width="100" height="55" rx="16" fill="#1e293b" stroke="#334155" strokeWidth="1" />

          {/* Eyes */}
          <circle cx="75" cy="77" r="10" fill="url(#robotVisorGrad)" filter="url(#robotGlow)">
            <animate attributeName="r" values="10;11;10" dur="3s" repeatCount="indefinite" />
          </circle>
          <circle cx="125" cy="77" r="10" fill="url(#robotVisorGrad)" filter="url(#robotGlow)">
            <animate attributeName="r" values="10;11;10" dur="3s" begin="0.3s" repeatCount="indefinite" />
          </circle>
          {/* Eye highlights */}
          <circle cx="72" cy="74" r="3.5" fill="rgba(255,255,255,0.7)" />
          <circle cx="122" cy="74" r="3.5" fill="rgba(255,255,255,0.7)" />

          {/* Mouth — dots animate fast when speaking */}
          <circle cx="88" cy="95" r="2.5" fill="rgba(255,255,255,0.5)">
            <animate attributeName="opacity" values={mouthValues} dur={mouthDur} repeatCount="indefinite" />
            {isSpeaking && <animate attributeName="cy" values="95;92;95" dur="0.25s" repeatCount="indefinite" />}
          </circle>
          <circle cx="100" cy="95" r="2.5" fill="rgba(255,255,255,0.5)">
            <animate attributeName="opacity" values={mouthValues} dur={mouthDur} begin="0.1s" repeatCount="indefinite" />
            {isSpeaking && <animate attributeName="cy" values="95;91;95" dur="0.3s" begin="0.08s" repeatCount="indefinite" />}
          </circle>
          <circle cx="112" cy="95" r="2.5" fill="rgba(255,255,255,0.5)">
            <animate attributeName="opacity" values={mouthValues} dur={mouthDur} begin="0.2s" repeatCount="indefinite" />
            {isSpeaking && <animate attributeName="cy" values="95;92;95" dur="0.28s" begin="0.15s" repeatCount="indefinite" />}
          </circle>

          {/* Ears */}
          <rect x="22" y="60" width="16" height="32" rx="6" fill="url(#robotBodyGrad)" stroke="#cbd5e1" strokeWidth="1" />
          <rect x="162" y="60" width="16" height="32" rx="6" fill="url(#robotBodyGrad)" stroke="#cbd5e1" strokeWidth="1" />
          {/* Ear indicators */}
          <circle cx="30" cy="76" r="3" fill={primaryColor} opacity="0.7">
            <animate attributeName="opacity" values="0.4;0.9;0.4" dur="2.5s" repeatCount="indefinite" />
          </circle>
          <circle cx="170" cy="76" r="3" fill={accentColor} opacity="0.7">
            <animate attributeName="opacity" values="0.4;0.9;0.4" dur="2.5s" begin="1s" repeatCount="indefinite" />
          </circle>

          {/* Neck */}
          <rect x="80" y="133" width="40" height="16" rx="4" fill="url(#robotBodyGrad)" stroke="#cbd5e1" strokeWidth="1" />

          {/* Shoulders / body */}
          <rect x="45" y="147" width="110" height="45" rx="16" fill="url(#robotBodyGrad)" stroke="#cbd5e1" strokeWidth="1" />

          {/* Chest light */}
          <circle cx="100" cy="170" r="8" fill="#e2e8f0" stroke="#cbd5e1" strokeWidth="1" />
          <circle cx="100" cy="170" r="5" fill={primaryColor} filter="url(#robotGlow)">
            <animate attributeName="opacity" values="0.4;1;0.4" dur="2s" repeatCount="indefinite" />
            <animate attributeName="r" values="5;6;5" dur="2s" repeatCount="indefinite" />
          </circle>

          {/* Circuit lines */}
          <path d="M70 160 L70 175 L85 175" stroke={primaryColor} strokeWidth="1" strokeOpacity="0.35" fill="none" strokeLinecap="round" />
          <path d="M130 160 L130 175 L115 175" stroke={accentColor} strokeWidth="1" strokeOpacity="0.35" fill="none" strokeLinecap="round" />
        </svg>
      </div>
    </div>
  );
};

export default AIRobot3D;
