import { useRef, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

export interface VideoTimestamp {
  start_time: number;
  end_time: number;
  text_preview: string;
  is_agent_cited?: boolean;
  /** Filename of the media the agent cited this timestamp for (used to disambiguate multiple media). */
  mediaLabel?: string;
}

interface VideoPlayerProps {
  videoUrl: string;
  timestamps: VideoTimestamp[];
  title?: string;
  isAudio?: boolean;
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) {
    return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  }
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
}

export default function VideoPlayer({ videoUrl, timestamps, title, isAudio = false }: Readonly<VideoPlayerProps>) {
  const { t } = useTranslation('common');
  const videoRef = useRef<HTMLVideoElement | HTMLAudioElement>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isExpanded, setIsExpanded] = useState(true);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onTime = () => setCurrentTime(video.currentTime);
    const onDuration = () => setDuration(video.duration);

    video.addEventListener('timeupdate', onTime);
    video.addEventListener('durationchange', onDuration);
    return () => {
      video.removeEventListener('timeupdate', onTime);
      video.removeEventListener('durationchange', onDuration);
    };
  }, []);

  const handleTimestampClick = (index: number) => {
    const video = videoRef.current;
    if (!video) return;
    setSelectedIndex(index);
    video.currentTime = timestamps[index].start_time;
    video.play().catch(() => {});
  };

  if (!videoUrl || timestamps.length === 0) return null;

  const hasCited = timestamps.some((t) => t.is_agent_cited);

  return (
    <div className="bg-surface dark:bg-surface-dark border border-line dark:border-line-dark rounded-lg overflow-hidden mt-2">
        {/* Header */}
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 bg-surface dark:bg-surface-dark border-b border-line dark:border-line-dark hover:bg-surface-hover dark:hover:bg-surface-hover-dark transition-colors"
        onClick={() => setIsExpanded((v) => !v)}
      >
        <span className="flex items-center gap-2 text-sm font-medium text-fg dark:text-fg-dark">
          <span className="text-accent dark:text-accent-dark">{hasCited ? '📍' : isAudio ? '🎵' : '🎬'}</span>
          {title ?? t('playgroundMedia.relevantMoments', { count: timestamps.length })}
        </span>
        <span className="text-fg-secondary dark:text-fg-secondary-dark text-xs">{isExpanded ? '▼' : '▲'}</span>
      </button>

      {isExpanded && (
        <div className="flex flex-col">
          {/* Media element */}
          {isAudio ? (
            <div className="bg-surface dark:bg-surface-dark px-4 py-3">
              <audio
                ref={videoRef as React.RefObject<HTMLAudioElement>}
                src={videoUrl}
                className="w-full"
                controls
                preload="metadata"
              />
            </div>
          ) : (
            <div className="bg-black">
              <video
                ref={videoRef as React.RefObject<HTMLVideoElement>}
                src={videoUrl}
                className="w-full aspect-video"
                controls
                preload="metadata"
              />
            </div>
          )}

          {/* Timeline bar */}
          {duration > 0 && (
            <div className="bg-surface dark:bg-surface-dark px-4 pt-5 pb-3 border-b border-line dark:border-line-dark">
              <div className="flex items-center gap-3">
                <span className="text-fg dark:text-fg-dark font-mono text-xs min-w-[40px]">{formatTime(currentTime)}</span>
                <div className="flex-1 h-2 bg-surface-hover dark:bg-surface-hover-dark rounded-full relative overflow-visible">
                  {/* Progress fill */}
                  <div
                    className="absolute inset-y-0 left-0 bg-accent/40 dark:bg-accent-dark/40 rounded-full transition-all duration-150"
                    style={{ width: `${(currentTime / duration) * 100}%` }}
                  />
                  {/* Timestamp markers */}
                  {timestamps.map((ts, i) => {
                    const left = Math.min((ts.start_time / duration) * 100, 100);
                    const width = Math.max(Math.min(((ts.end_time - ts.start_time) / duration) * 100, 100 - left), 2);
                    const isSelected = selectedIndex === i;
                    return (
                      <button
                        type="button"
                        key={`${ts.start_time}-${ts.end_time}`}
                        className={`absolute top-1/2 h-3 -translate-y-1/2 cursor-pointer rounded-full transition-colors ${
                          isSelected
                            ? 'bg-accent dark:bg-accent-dark'
                            : ts.is_agent_cited
                              ? 'bg-bronze hover:opacity-80 dark:bg-bronze-dark'
                              : 'bg-ink/40 hover:bg-ink/60 dark:bg-ink-dark/40 dark:hover:bg-ink-dark/60'
                        }`}
                        style={{
                          left: `${left}%`,
                          width: `${width}%`,
                          minWidth: '6px',
                          zIndex: isSelected ? 15 : 10
                        }}
                        onClick={() => handleTimestampClick(i)}
                        title={`${formatTime(ts.start_time)} - ${formatTime(ts.end_time)}`}
                      />
                    );
                  })}
                  {/* Playhead */}
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-3 h-3 bg-surface dark:bg-surface-dark rounded-full border-2 border-accent dark:border-accent-dark pointer-events-none"
                    style={{
                      left: `calc(${(currentTime / duration) * 100}% - 6px)`,
                      zIndex: 30
                    }}
                  />
                </div>
                <span className="text-fg-secondary dark:text-fg-secondary-dark font-mono text-xs min-w-[40px] text-right">{formatTime(duration)}</span>
              </div>
            </div>
          )}

          {/* Timestamp buttons */}
          <div className="bg-surface dark:bg-surface-dark border-t border-line dark:border-line-dark p-3">
            <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark mb-2">
              {t('playgroundMedia.jumpToMentionedMoments')}
            </p>
            <div className="flex flex-wrap gap-2">
              {timestamps.map((ts, i) => (
                <button
                  type="button"
                  key={`btn-${ts.start_time}-${ts.end_time}`}
                  onClick={() => handleTimestampClick(i)}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
                    selectedIndex === i
                      ? 'bg-ink text-ink-on dark:bg-ink-dark dark:text-ink-on-dark'
                      : 'bg-surface-hover text-fg-secondary hover:bg-surface-ash dark:bg-surface-hover-dark dark:text-fg-secondary-dark dark:hover:bg-surface-dark'
                  }`}
                  title={ts.text_preview}
                >
                  {ts.is_agent_cited && <span className="text-bronze dark:text-bronze-dark">📍</span>}
                  <span className="font-mono">
                    {formatTime(ts.start_time)}
                  </span>
                  {formatTime(ts.start_time) !== formatTime(ts.end_time) && (
                    <span className="font-mono">
                      - {formatTime(ts.end_time)}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

        </div>
      )}
    </div>
  );
}