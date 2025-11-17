import React from 'react';

interface UsageStats {
  usage_percentage: number;
  stress_level: 'low' | 'moderate' | 'high' | 'critical' | 'unlimited';
  current_usage: number;
  limit: number;
  remaining: number;
  reset_in_seconds: number;
  is_over_limit: boolean;
}

interface SpeedometerProps {
  usageStats: UsageStats;
  size?: 'sm' | 'md' | 'lg';
  showDetails?: boolean;
}

const Speedometer: React.FC<SpeedometerProps> = ({ 
  usageStats, 
  size = 'md', 
  showDetails = false 
}) => {
  const { 
    usage_percentage, 
    stress_level, 
    current_usage, 
    limit, 
    remaining, 
    reset_in_seconds,
    is_over_limit 
  } = usageStats;

  // Size configurations
  const sizeConfig = {
    sm: { size: 40, strokeWidth: 4, fontSize: 'text-xs' },
    md: { size: 60, strokeWidth: 6, fontSize: 'text-sm' },
    lg: { size: 80, strokeWidth: 8, fontSize: 'text-base' }
  };

  const config = sizeConfig[size];
  const radius = (config.size - config.strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const strokeDasharray = circumference;
  const strokeDashoffset = circumference - (usage_percentage / 100) * circumference;

  // Color based on stress level
  const getColor = () => {
    if (stress_level === 'unlimited') return '#10B981'; // green
    if (stress_level === 'low') return '#10B981'; // green
    if (stress_level === 'moderate') return '#F59E0B'; // yellow
    if (stress_level === 'high') return '#F97316'; // orange
    if (stress_level === 'critical') return '#EF4444'; // red
    return '#6B7280'; // gray
  };

  const getBgColor = () => {
    if (stress_level === 'unlimited') return 'bg-green-50';
    if (stress_level === 'low') return 'bg-green-50';
    if (stress_level === 'moderate') return 'bg-yellow-50';
    if (stress_level === 'high') return 'bg-orange-50';
    if (stress_level === 'critical') return 'bg-red-50';
    return 'bg-gray-50';
  };

  const getTextColor = () => {
    if (stress_level === 'unlimited') return 'text-green-700';
    if (stress_level === 'low') return 'text-green-700';
    if (stress_level === 'moderate') return 'text-yellow-700';
    if (stress_level === 'high') return 'text-orange-700';
    if (stress_level === 'critical') return 'text-red-700';
    return 'text-gray-700';
  };

  const formatTime = (seconds: number) => {
    if (seconds <= 0) return '0s';
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  const getStressIcon = () => {
    if (stress_level === 'unlimited') return '∞';
    if (stress_level === 'low') return '🟢';
    if (stress_level === 'moderate') return '🟡';
    if (stress_level === 'high') return '🟠';
    if (stress_level === 'critical') return '🔴';
    return '⚪';
  };

  return (
    <div className={`inline-flex flex-col items-center ${getBgColor()} rounded-lg p-2`}>
      <div className="relative">
        <svg
          width={config.size}
          height={config.size}
          className="transform -rotate-90"
        >
          {/* Background circle */}
          <circle
            cx={config.size / 2}
            cy={config.size / 2}
            r={radius}
            stroke="#E5E7EB"
            strokeWidth={config.strokeWidth}
            fill="none"
          />
          {/* Progress circle */}
          <circle
            cx={config.size / 2}
            cy={config.size / 2}
            r={radius}
            stroke={getColor()}
            strokeWidth={config.strokeWidth}
            fill="none"
            strokeDasharray={strokeDasharray}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            className="transition-all duration-300 ease-in-out"
          />
        </svg>
        
        {/* Center content */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className={`font-bold ${getTextColor()} ${config.fontSize}`}>
            {stress_level === 'unlimited' ? '∞' : `${Math.round(usage_percentage)}%`}
          </div>
          {size !== 'sm' && (
            <div className={`text-xs ${getTextColor()} opacity-75`}>
              {stress_level === 'unlimited' ? 'Unlimited' : stress_level}
            </div>
          )}
        </div>
      </div>

      {/* Details */}
      {showDetails && (
        <div className="mt-2 text-center">
          <div className={`text-xs ${getTextColor()} font-medium`}>
            {getStressIcon()} {stress_level.charAt(0).toUpperCase() + stress_level.slice(1)}
          </div>
          <div className="text-xs text-gray-600 mt-1">
            {current_usage}/{limit === 0 ? '∞' : limit} calls
          </div>
          {limit > 0 && (
            <div className="text-xs text-gray-500">
              Resets in {formatTime(reset_in_seconds)}
            </div>
          )}
          {is_over_limit && (
            <div className="text-xs text-red-600 font-medium">
              Over limit!
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Speedometer;

