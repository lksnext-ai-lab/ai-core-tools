import { ArrowDown, ArrowUp, Layers } from 'lucide-react';
import type { MiddlewareType } from '../../core/types';
import { MIDDLEWARE_TYPE_INFO, middlewareTypeLabel } from '../../constants/middlewares';

export interface AgentMiddlewareOption {
  middleware_id: number;
  name: string;
  description?: string;
  middleware_type: MiddlewareType;
}

interface AgentMiddlewaresCardProps {
  readonly middlewares: AgentMiddlewareOption[];
  /** Selected ids in execution order. */
  readonly selectedIds: number[];
  readonly hasMemory: boolean;
  readonly onChange: (ids: number[]) => void;
  /** Human approval needs conversation memory to pause and resume. */
  readonly onRequireMemory: () => void;
  readonly onManage: () => void;
}

/** Pick an agent's middlewares (one per type) and their execution order. */
function AgentMiddlewaresCard({
  middlewares, selectedIds, hasMemory, onChange, onRequireMemory, onManage,
}: AgentMiddlewaresCardProps) {
  const byId = new Map(middlewares.map((m) => [m.middleware_id, m]));
  const selected = selectedIds.map((id) => byId.get(id)).filter((m): m is AgentMiddlewareOption => !!m);
  const selectedTypes = new Set(selected.map((m) => m.middleware_type));

  const toggle = (mw: AgentMiddlewareOption) => {
    if (selectedIds.includes(mw.middleware_id)) {
      onChange(selectedIds.filter((id) => id !== mw.middleware_id));
      return;
    }
    if (mw.middleware_type === 'human_in_the_loop' && !hasMemory) {
      onRequireMemory();
    }
    onChange([...selectedIds, mw.middleware_id]);
  };

  const move = (index: number, delta: -1 | 1) => {
    const next = selected.map((m) => m.middleware_id);
    const target = index + delta;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
      <div className="mb-6">
        <h3 className="text-xl font-semibold text-gray-900 flex items-center">
          <Layers className="w-5 h-5 mr-3" />
          {' '}Middlewares
        </h3>
        <p className="text-gray-600 mt-1">Add safety, approval and cost controls that run around every model and tool call</p>
      </div>

      {middlewares.length === 0 ? (
        <div className="text-center py-8">
          <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <Layers className="w-8 h-8 text-gray-400" />
          </div>
          <h4 className="text-lg font-medium text-gray-900 mb-2">No Middlewares Available</h4>
          <p className="text-gray-500 mb-4">Create middlewares in this app to reuse them across agents.</p>
          <button
            type="button"
            onClick={onManage}
            className="inline-flex items-center px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <Layers className="w-4 h-4 mr-2" />
            {' '}Manage Middlewares
          </button>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {middlewares.map((mw) => {
              const isSelected = selectedIds.includes(mw.middleware_id);
              // LangChain allows one middleware of each type per agent.
              const blocked = !isSelected && selectedTypes.has(mw.middleware_type);
              const hintId = `mw-hint-${mw.middleware_id}`;
              return (
                <label
                  key={mw.middleware_id}
                  className={`p-4 rounded-xl border-2 transition-all duration-200 text-left w-full ${
                    blocked
                      ? 'border-gray-200 bg-gray-50 opacity-60 cursor-not-allowed'
                      : isSelected
                        ? 'border-indigo-500 bg-indigo-50 cursor-pointer'
                        : 'border-gray-200 bg-gray-50 hover:border-gray-300 cursor-pointer'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center min-w-0">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        disabled={blocked}
                        onChange={() => toggle(mw)}
                        aria-describedby={hintId}
                        className="w-4 h-4 shrink-0 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="ml-3 text-sm font-medium text-gray-900 truncate">{mw.name}</span>
                    </div>
                    {mw.name !== middlewareTypeLabel(mw.middleware_type) && (
                      <span className="shrink-0 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800">
                        {middlewareTypeLabel(mw.middleware_type)}
                      </span>
                    )}
                  </div>
                  <p id={hintId} className="mt-2 ml-7 text-xs text-gray-500">
                    {blocked
                      ? `Only one ${middlewareTypeLabel(mw.middleware_type).toLowerCase()} middleware per agent.`
                      : mw.description || MIDDLEWARE_TYPE_INFO[mw.middleware_type]?.description}
                  </p>
                  {mw.middleware_type === 'human_in_the_loop' && !isSelected && !blocked && !hasMemory && (
                    <p className="mt-1 ml-7 text-xs text-indigo-700">Selecting it turns on conversation memory.</p>
                  )}
                </label>
              );
            })}
          </div>

          {selected.length > 1 && (
            <div className="mt-6">
              <h4 className="text-sm font-semibold text-gray-900">Execution order</h4>
              <p className="text-xs text-gray-500 mb-2">Middlewares run top to bottom around each model call (summarization always runs first).</p>
              <ol className="space-y-2">
                {selected.map((mw, index) => (
                  <li
                    key={mw.middleware_id}
                    className="flex items-center justify-between gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2"
                  >
                    <span className="text-sm text-gray-900 min-w-0 truncate">
                      <span className="text-gray-500 tabular-nums mr-2">{index + 1}.</span>
                      {mw.name}
                    </span>
                    <span className="flex shrink-0 gap-1">
                      <button
                        type="button"
                        onClick={() => move(index, -1)}
                        disabled={index === 0}
                        aria-label={`Move ${mw.name} up`}
                        className="p-1 rounded text-gray-600 hover:bg-gray-200 disabled:opacity-30 disabled:hover:bg-transparent"
                      >
                        <ArrowUp className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => move(index, 1)}
                        disabled={index === selected.length - 1}
                        aria-label={`Move ${mw.name} down`}
                        className="p-1 rounded text-gray-600 hover:bg-gray-200 disabled:opacity-30 disabled:hover:bg-transparent"
                      >
                        <ArrowDown className="w-4 h-4" />
                      </button>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default AgentMiddlewaresCard;
