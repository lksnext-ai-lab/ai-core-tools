import { useEffect, useRef } from 'react';

interface AudioMessageProps {
    audioUrl: string;
    transcript?: string;
    onPlay?: () => void;
    onEnded?: () => void;
    onPause?: () => void;
}

export default function AudioMessage({
    audioUrl,
    transcript,
    onPlay,
    onEnded,
    onPause,
}: AudioMessageProps) {
    const audioRef = useRef<HTMLAudioElement>(null);

    useEffect(() => {
        const audio = audioRef.current;

        if (!audio) return;

        audio.play().catch((err) => {
            console.warn('Autoplay blocked: ', err);
        })
    }, []);

    return (
        <div className="space-y-2">
            <audio
                ref={audioRef}
                controls
                src={audioUrl}
                className="w-full min-w-[500px]"
                onPlay={onPlay}
                onEnded={onEnded}
                onPause={onPause}
            />

            {transcript && (
                <details className="text-xs text-gray-500 dark:text-gray-400">
                    <summary className="cursor-pointer">Show transcript</summary>
                    <p className="mt-1 whitespace-pre-wrap">{transcript}</p>
                </details>
            )}
        </div>
    )
}