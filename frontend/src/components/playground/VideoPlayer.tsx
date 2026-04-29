import { useRef, useState, useEffect } from 'react';

export interface VideoTimestamp {
  start_time: number;
  end_time: number;
  text_preview: string;
  is_agent_cited?: boolean;
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
  const videoRef = useRef<HTMLVideoElement | HTMLAudioElement>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isExpanded, setIsExpanded] = useState(false);

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
    <div className="bg-gray-900 rounded-lg overflow-hidden shadow-lg mt-2">
      {/* Header */}
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-2 bg-gray-800 hover:bg-gray-700 transition-colors"
        onClick={() => setIsExpanded((v) => !v)}
      >
        <span className="flex items-center gap-2 text-sm font-medium text-white">
          <span className="text-purple-400">{hasCited ? '📍' : isAudio ? '🎵' : '🎬'}</span>
          {title ?? `Momentos relevantes (${timestamps.length})`}
        </span>
        <span className="text-gray-400 text-xs">{isExpanded ? '▼' : '▲'}</span>
      </button>

      {isExpanded && (
        <div className="flex flex-col">
          {/* Media element */}
          {isAudio ? (
            <div className="bg-gray-900 px-4 py-3">
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
            <div className="bg-gray-900 px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="text-white font-mono text-xs min-w-[40px]">{formatTime(currentTime)}</span>
                <div className="flex-1 h-5 bg-gray-700 rounded relative overflow-visible">
                  {/* Progress fill */}
                  <div
                    className="absolute inset-y-0 left-0 bg-purple-600/40 rounded transition-all duration-150"
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
                        className={`absolute top-0 bottom-0 cursor-pointer transition-all rounded ${
                          isSelected
                            ? 'bg-green-400 shadow-lg shadow-green-500/50'
                            : ts.is_agent_cited
                              ? 'bg-yellow-400 hover:bg-yellow-300'
                              : 'bg-blue-400 hover:bg-blue-300'
                        }`}
                        style={{ left: `${left}%`, width: `${width}%`, minWidth: '6px', zIndex: isSelected ? 15 : 10 }}
                        onClick={() => handleTimestampClick(i)}
                        title={`${formatTime(ts.start_time)} - ${formatTime(ts.end_time)}`}
                      />
                    );
                  })}
                  {/* Playhead */}
                  <div
                    className="absolute top-1/2 -translate-y-1/2 w-4 h-4 bg-white rounded-full shadow border-2 border-purple-500 pointer-events-none"
                    style={{ left: `calc(${(currentTime / duration) * 100}% - 8px)`, zIndex: 30 }}
                  />
                </div>
                <span className="text-gray-400 font-mono text-xs min-w-[40px] text-right">{formatTime(duration)}</span>
              </div>
            </div>
          )}

          {/* Timestamp buttons */}
          <div className="bg-gray-800 p-3">
            <p className="text-xs text-gray-500 mb-2">Salta a los momentos mencionados:</p>
            <div className="flex flex-wrap gap-2">
              {timestamps.map((ts, i) => (
                <button
                  type="button"
                  key={`btn-${ts.start_time}-${ts.end_time}`}
                  onClick={() => handleTimestampClick(i)}
                  className={`flex items-center gap-1 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                    selectedIndex === i
                      ? 'bg-purple-600 text-white ring-2 ring-purple-400'
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600 hover:text-white'
                  }`}
                  title={ts.text_preview}
                >
                  {ts.is_agent_cited && <span className="text-yellow-300">📍</span>}
                  <span className="font-mono">{formatTime(ts.start_time)}</span>
                  {formatTime(ts.start_time) !== formatTime(ts.end_time) && (
                    <span className="text-gray-400 font-mono">- {formatTime(ts.end_time)}</span>
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