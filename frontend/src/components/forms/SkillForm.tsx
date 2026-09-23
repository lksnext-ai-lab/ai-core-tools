import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  File,
  FileText,
  Folder,
  Info,
  Loader2,
  X,
} from 'lucide-react';
import FormActions from './FormActions';
import { FormField, FormTextArea, FormCheckbox } from '../ui/FormField';
import { FormError } from '../ui/FormError';
import { Badge } from '../ui/Badge';
import ReadOnlyBanner from '../ui/ReadOnlyBanner';
import { apiService, ApiError } from '../../services/api';
import { errorMessage } from '../../constants/messages';
import type { Skill, SkillFileInfo } from '../../core/types';

export interface SkillFormSubmitData {
  readonly name: string;
  readonly description: string;
  readonly content: string;
  readonly display_name: string | null;
  readonly when_to_use: string | null;
  readonly allowed_tools: string[];
  readonly runtime: string | null;
  readonly bootstrap_script_path: string | null;
  readonly runtime_options: Record<string, unknown> | null;
  readonly is_enabled: boolean;
}

interface SkillFormProps {
  readonly skill?: Skill | null;
  /**
   * Explicit override for the read-only gate, decoupled from `skill.is_system`. Defaults to
   * `Boolean(skill?.is_system)` when not provided — that default is correct for the app-scoped
   * SkillsPage (a non-admin looking at an inherited system skill they can't touch), but the
   * admin System Skills page must pass `readOnly={false}` explicitly so platform admins can
   * actually edit system skills there.
   */
  readonly readOnly?: boolean;
  readonly onSubmit: (data: SkillFormSubmitData) => Promise<void>;
  readonly onCancel: () => void;
}

interface SkillFormState {
  name: string;
  description: string;
  content: string;
  display_name: string;
  when_to_use: string;
  allowed_tools: string[];
  runtime: string;
  bootstrap_script_path: string;
  runtime_options_text: string;
  is_enabled: boolean;
}

const EMPTY_STATE: SkillFormState = {
  name: '',
  description: '',
  content: '',
  display_name: '',
  when_to_use: '',
  allowed_tools: [],
  runtime: '',
  bootstrap_script_path: '',
  runtime_options_text: '',
  is_enabled: true,
};

function stateFromSkill(skill: Skill | null | undefined): SkillFormState {
  if (!skill) return EMPTY_STATE;

  const frontmatter = skill.frontmatter ?? {};
  const whenToUse = typeof frontmatter['when_to_use'] === 'string' ? (frontmatter['when_to_use'] as string) : '';
  const runtimeOptions = skill.runtime_options;
  const runtimeOptionsText =
    runtimeOptions && Object.keys(runtimeOptions).length > 0 ? JSON.stringify(runtimeOptions, null, 2) : '';

  return {
    name: skill.name ?? '',
    description: skill.description ?? '',
    content: skill.content ?? '',
    display_name: skill.display_name ?? '',
    when_to_use: whenToUse,
    allowed_tools: skill.allowed_tools ? [...skill.allowed_tools] : [],
    runtime: skill.runtime ?? '',
    bootstrap_script_path: skill.bootstrap_script_path ?? '',
    runtime_options_text: runtimeOptionsText,
    is_enabled: skill.is_enabled ?? true,
  };
}

// ==================== Allowed tools chip input (case-preserving; TagInput lowercases, which
// would silently corrupt tool names like "WebSearch") ====================

interface AllowedToolsInputProps {
  readonly tools: string[];
  readonly onChange: (tools: string[]) => void;
  readonly disabled: boolean;
}

function AllowedToolsInput({ tools, onChange, disabled }: AllowedToolsInputProps) {
  const [draft, setDraft] = useState('');
  const [announcement, setAnnouncement] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const removeButtonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const addTool = useCallback(
    (raw: string) => {
      const trimmed = raw.trim();
      if (!trimmed || tools.includes(trimmed)) {
        setDraft('');
        return;
      }
      onChange([...tools, trimmed]);
      setAnnouncement(`Added tool ${trimmed}`);
      setDraft('');
    },
    [tools, onChange],
  );

  const removeTool = useCallback(
    (index: number) => {
      const removed = tools[index];
      onChange(tools.filter((_, i) => i !== index));
      if (removed) setAnnouncement(`Removed tool ${removed}`);
      // Move focus to the previous chip's remove button, or back to the input if none remain —
      // otherwise focus falls to <body> when the removed button unmounts.
      requestAnimationFrame(() => {
        const previous = removeButtonRefs.current[index - 1];
        if (previous) previous.focus();
        else inputRef.current?.focus();
      });
    },
    [tools, onChange],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      addTool(draft);
    } else if (e.key === 'Backspace' && !draft && tools.length > 0) {
      removeTool(tools.length - 1);
    }
  };

  return (
    <div>
      <span role="status" aria-live="polite" className="sr-only">
        {announcement}
      </span>
      <div className="flex flex-wrap items-center gap-2 p-2 border border-gray-300 dark:border-gray-600 rounded-xl min-h-[44px] bg-white dark:bg-gray-800 focus-within:ring-2 focus-within:ring-purple-500 focus-within:border-purple-500 transition-all">
        {tools.map((tool, idx) => (
          <span
            key={tool}
            className="inline-flex items-center gap-1 text-sm font-mono bg-purple-100 dark:bg-purple-900/40 text-purple-800 dark:text-purple-200 px-2.5 py-1 rounded-full"
          >
            {tool}
            {!disabled && (
              <button
                type="button"
                ref={(el) => { removeButtonRefs.current[idx] = el; }}
                onClick={() => removeTool(idx)}
                className="ml-0.5 text-purple-600 dark:text-purple-300 hover:text-purple-900 dark:hover:text-purple-100 font-medium"
                aria-label={`Remove allowed tool ${tool}`}
              >
                <X className="w-3 h-3" aria-hidden="true" />
              </button>
            )}
          </span>
        ))}
        {!disabled && (
          <input
            id="allowed_tools"
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            onBlur={() => addTool(draft)}
            placeholder={tools.length === 0 ? 'e.g. Bash, WebSearch — Enter or comma to add' : ''}
            aria-describedby="allowed_tools_help"
            className="flex-1 min-w-[140px] border-none outline-none text-sm bg-transparent py-1 px-1 dark:text-gray-100"
          />
        )}
        {disabled && tools.length === 0 && (
          <span className="text-sm text-gray-400 dark:text-gray-500 italic">No allowed tools declared</span>
        )}
      </div>
      <p id="allowed_tools_help" className="mt-1 flex items-start gap-1 text-xs text-gray-500 dark:text-gray-400">
        <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" aria-hidden="true" />
        <span>
          Informational metadata only — stored, imported/exported and displayed, but <strong>not enforced</strong>{' '}
          against the agent&apos;s tool set.
        </span>
      </p>
    </div>
  );
}

// ==================== Read-only resource file tree ====================

interface FileTreeNode {
  name: string;
  path: string;
  isFile: boolean;
  info?: SkillFileInfo;
  children: FileTreeNode[];
}

function buildFileTree(files: SkillFileInfo[]): FileTreeNode[] {
  const root: FileTreeNode[] = [];

  const findOrCreate = (siblings: FileTreeNode[], name: string, path: string, isFile: boolean): FileTreeNode => {
    const existing = siblings.find((n) => n.name === name);
    if (existing) return existing;
    const node: FileTreeNode = { name, path, isFile, children: [] };
    siblings.push(node);
    return node;
  };

  for (const file of files) {
    const parts = file.path.split('/').filter(Boolean);
    if (parts.length === 0) continue;

    let level = root;
    let currentPath = '';
    parts.forEach((part, index) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part;
      const isLast = index === parts.length - 1;
      const node = findOrCreate(level, part, currentPath, isLast);
      if (isLast) {
        node.isFile = true;
        node.info = file;
      }
      level = node.children;
    });
  }

  const sortTree = (nodes: FileTreeNode[]): FileTreeNode[] =>
    nodes
      .map((node) => ({ ...node, children: sortTree(node.children) }))
      .sort((a, b) => {
        if (a.isFile !== b.isFile) return a.isFile ? 1 : -1;
        return a.name.localeCompare(b.name);
      });

  return sortTree(root);
}

function collectFolderPaths(nodes: FileTreeNode[]): string[] {
  const paths: string[] = [];
  for (const node of nodes) {
    if (!node.isFile) {
      paths.push(node.path);
      paths.push(...collectFolderPaths(node.children));
    }
  }
  return paths;
}

type PreviewState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'loaded'; content: string }
  | { status: 'error'; message: string };

const PADDING_CLASSES = ['pl-2', 'pl-4', 'pl-6', 'pl-8', 'pl-10', 'pl-12'];

function paddingClassForDepth(depth: number): string {
  return PADDING_CLASSES[Math.min(depth, PADDING_CLASSES.length - 1)];
}

function domIdForPath(prefix: string, path: string): string {
  return `${prefix}-${path.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
}

interface FileTreeViewProps {
  readonly nodes: FileTreeNode[];
  readonly depth?: number;
  readonly expandedFolders: Set<string>;
  readonly onToggleFolder: (path: string) => void;
  readonly expandedFiles: Set<string>;
  readonly previews: Record<string, PreviewState>;
  readonly onToggleFile: (node: FileTreeNode) => void;
}

function FileTreeView({
  nodes,
  depth = 0,
  expandedFolders,
  onToggleFolder,
  expandedFiles,
  previews,
  onToggleFile,
}: FileTreeViewProps) {
  return (
    <ul className="space-y-0.5">
      {nodes.map((node) => {
        if (!node.isFile) {
          const isOpen = expandedFolders.has(node.path);
          const contentId = domIdForPath('skill-folder-content', node.path);
          return (
            <li key={node.path}>
              <button
                type="button"
                onClick={() => onToggleFolder(node.path)}
                aria-expanded={isOpen}
                aria-controls={contentId}
                className={`w-full flex items-center gap-2 rounded py-1 pr-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700/60 ${paddingClassForDepth(depth)}`}
                title={node.path}
              >
                {isOpen ? (
                  <ChevronDown className="w-3.5 h-3.5 shrink-0 text-gray-400" aria-hidden="true" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 shrink-0 text-gray-400" aria-hidden="true" />
                )}
                <Folder className="w-4 h-4 shrink-0 text-amber-500" aria-hidden="true" />
                <span className="min-w-0 truncate font-mono text-xs">{node.name}</span>
              </button>
              {isOpen && node.children.length > 0 && (
                <div id={contentId}>
                  <FileTreeView
                    nodes={node.children}
                    depth={depth + 1}
                    expandedFolders={expandedFolders}
                    onToggleFolder={onToggleFolder}
                    expandedFiles={expandedFiles}
                    previews={previews}
                    onToggleFile={onToggleFile}
                  />
                </div>
              )}
            </li>
          );
        }

        const info = node.info;
        const isText = info?.is_text ?? false;
        const isOpen = expandedFiles.has(node.path);
        const preview = previews[node.path] ?? { status: 'idle' };
        const sizeLabel =
          info?.size_bytes !== undefined ? `${info.size_bytes.toLocaleString()} bytes` : undefined;

        const previewId = domIdForPath('skill-file-preview', node.path);

        return (
          <li key={node.path}>
            {isText ? (
              <button
                type="button"
                onClick={() => onToggleFile(node)}
                aria-expanded={isOpen}
                aria-controls={previewId}
                className={`w-full flex items-center gap-2 rounded py-1 pr-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700/60 ${paddingClassForDepth(depth)}`}
                title={node.path}
              >
                {isOpen ? (
                  <ChevronDown className="w-3.5 h-3.5 shrink-0 text-gray-400" aria-hidden="true" />
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 shrink-0 text-gray-400" aria-hidden="true" />
                )}
                <FileText className="w-4 h-4 shrink-0 text-gray-400" aria-hidden="true" />
                <span className="min-w-0 truncate font-mono text-xs">{node.name}</span>
                {sizeLabel && (
                  <span className="ml-auto shrink-0 text-xs text-gray-400">{sizeLabel}</span>
                )}
              </button>
            ) : (
              <div
                className={`flex items-center gap-2 py-1 pr-2 text-sm text-gray-500 dark:text-gray-400 ${paddingClassForDepth(depth)}`}
                title={node.path}
              >
                <span className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                <File className="w-4 h-4 shrink-0 text-gray-400" aria-hidden="true" />
                <span className="min-w-0 truncate font-mono text-xs">{node.name}</span>
                <span className="ml-auto shrink-0 text-xs text-gray-400 italic">
                  binary — {info?.size_bytes?.toLocaleString() ?? 0} bytes
                </span>
              </div>
            )}

            {isText && isOpen && (
              <div
                id={previewId}
                role="status"
                aria-live="polite"
                className={`${paddingClassForDepth(Math.min(depth + 1, PADDING_CLASSES.length - 1))} pb-2`}
              >
                {preview.status === 'loading' && (
                  <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 py-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
                    Loading preview…
                  </div>
                )}
                {preview.status === 'error' && (
                  <p className="flex items-start gap-1 text-xs text-red-600 dark:text-red-400 py-1">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" aria-hidden="true" />
                    <span>{preview.message}</span>
                  </p>
                )}
                {preview.status === 'loaded' && (
                  <pre className="max-h-56 overflow-auto rounded border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 p-2 text-xs font-mono text-gray-800 dark:text-gray-200 whitespace-pre-wrap break-words">
                    {preview.content}
                  </pre>
                )}
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// ==================== Main form ====================

function SkillForm({ skill, readOnly, onSubmit, onCancel }: Readonly<SkillFormProps>) {
  const { appId } = useParams();
  const [formState, setFormState] = useState<SkillFormState>(() => stateFromSkill(skill));
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!skill && skill.skill_id !== 0;
  const isReadOnly = readOnly ?? Boolean(skill?.is_system);
  const disabled = isSubmitting || isReadOnly;

  const files = useMemo(() => skill?.files ?? [], [skill]);
  const fileTree = useMemo(() => buildFileTree(files), [files]);

  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set());
  const [expandedFiles, setExpandedFiles] = useState<Set<string>>(new Set());
  const [previews, setPreviews] = useState<Record<string, PreviewState>>({});

  // Guards against a preview fetch for a previously-open skill resolving AFTER the user has
  // switched to a different skill and repopulating `previews` under the wrong skill's state.
  const activeSkillIdRef = useRef<number | null>(skill?.skill_id ?? null);

  useEffect(() => {
    activeSkillIdRef.current = skill?.skill_id ?? null;
    setFormState(stateFromSkill(skill));
    setError(null);
    // Resource tree defaults to fully expanded folders (browsing structure is cheap); file
    // previews always start collapsed — content is fetched only when a file is opened.
    setExpandedFolders(new Set(collectFolderPaths(buildFileTree(skill?.files ?? []))));
    setExpandedFiles(new Set());
    setPreviews({});
  }, [skill]);

  const handleToggleFolder = useCallback((path: string) => {
    setExpandedFolders((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const handleToggleFile = useCallback(
    (node: FileTreeNode) => {
      const path = node.path;
      const willOpen = !expandedFiles.has(path);

      setExpandedFiles((prev) => {
        const next = new Set(prev);
        if (willOpen) next.add(path);
        else next.delete(path);
        return next;
      });

      if (!willOpen) return;
      const existing = previews[path];
      if (existing && (existing.status === 'loaded' || existing.status === 'loading')) return;
      if (!skill) return;

      const targetSkillId = skill.skill_id;
      const applyIfStillCurrent = (updater: (prev: Record<string, PreviewState>) => Record<string, PreviewState>) => {
        // Skip stale results — the user may have switched skills before this promise settled.
        if (activeSkillIdRef.current !== targetSkillId) return;
        setPreviews(updater);
      };

      // The app-scoped route (when :appId is present, i.e. we're rendered from the app-scoped
      // SkillsPage) already serves file content for both own-app skills AND enabled system
      // skills inherited by the app — prefer it whenever available, since it's reachable by any
      // app viewer and doesn't require platform-admin rights. Only fall back to the admin-only
      // system-scoped route when there's no :appId (i.e. we're rendered from the admin System
      // Skills page, which only ever shows system skills).
      let fetchPromise: Promise<{ content: string }>;
      if (appId) {
        const parsedAppId = Number.parseInt(appId, 10);
        if (Number.isNaN(parsedAppId)) return;
        fetchPromise = apiService.getSkillFileContent(parsedAppId, skill.skill_id, path);
      } else if (skill.is_system) {
        fetchPromise = apiService.getSystemSkillFileContent(skill.skill_id, path);
      } else {
        return;
      }

      applyIfStillCurrent((prev) => ({ ...prev, [path]: { status: 'loading' } }));
      fetchPromise
        .then((result) => {
          applyIfStillCurrent((prev) => ({ ...prev, [path]: { status: 'loaded', content: result.content } }));
        })
        .catch((err: unknown) => {
          const message =
            err instanceof ApiError && err.status === 404
              ? 'Preview is not available for this file.'
              : errorMessage(err, 'Failed to load file preview');
          applyIfStillCurrent((prev) => ({ ...prev, [path]: { status: 'error', message } }));
        });
    },
    [appId, skill, expandedFiles, previews],
  );

  const runtimeOptionsValidation = useMemo((): { valid: true; value: Record<string, unknown> | null } | { valid: false; error: string } => {
    const text = formState.runtime_options_text.trim();
    if (!text) return { valid: true, value: null };
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch (err) {
      return { valid: false, error: err instanceof Error ? `Invalid JSON: ${err.message}` : 'Invalid JSON' };
    }
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
      return { valid: false, error: 'Runtime options must be a JSON object, e.g. {"key": "value"}' };
    }
    return { valid: true, value: parsed as Record<string, unknown> };
  }, [formState.runtime_options_text]);

  const isValid =
    formState.name.trim() !== '' &&
    formState.description.trim() !== '' &&
    formState.content.trim() !== '' &&
    runtimeOptionsValidation.valid;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isReadOnly) return;

    if (!formState.name.trim()) {
      setError('Skill name is required');
      return;
    }
    if (!formState.description.trim()) {
      setError('Skill description is required');
      return;
    }
    if (!formState.content.trim()) {
      setError('Skill content is required');
      return;
    }
    if ('error' in runtimeOptionsValidation) {
      setError(runtimeOptionsValidation.error);
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const payload: SkillFormSubmitData = {
        name: formState.name.trim(),
        description: formState.description.trim(),
        content: formState.content,
        display_name: formState.display_name.trim() || null,
        when_to_use: formState.when_to_use.trim(),
        allowed_tools: formState.allowed_tools,
        runtime: formState.runtime.trim() || null,
        bootstrap_script_path: formState.bootstrap_script_path.trim() || null,
        runtime_options: runtimeOptionsValidation.value,
        is_enabled: formState.is_enabled,
      };
      await onSubmit(payload);
    } catch (err) {
      setError(errorMessage(err, 'Failed to save skill'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {isReadOnly && <ReadOnlyBanner userRole="viewer" minRole="platform administrators" />}

      <FormError error={error} />

      <FormField
        label="Name"
        id="name"
        value={formState.name}
        onChange={(e) => setFormState((prev) => ({ ...prev, name: e.target.value }))}
        placeholder="e.g., code_review_guidelines"
        disabled={disabled}
        required
        helpText="Short, unique identifier for the skill."
      />

      <FormField
        label="Display Name"
        id="display_name"
        value={formState.display_name}
        onChange={(e) => setFormState((prev) => ({ ...prev, display_name: e.target.value }))}
        placeholder="e.g., Code Review Guidelines"
        disabled={disabled}
        helpText="Human-friendly label shown in the UI. Defaults to the name if left blank."
      />

      <FormField
        label="Description"
        id="description"
        value={formState.description}
        onChange={(e) => setFormState((prev) => ({ ...prev, description: e.target.value }))}
        placeholder="e.g., Best practices for reviewing code quality"
        disabled={disabled}
        required
        helpText="The agent sees this description to decide when the skill is relevant."
      />

      <FormTextArea
        label="When to Use"
        id="when_to_use"
        value={formState.when_to_use}
        onChange={(e) => setFormState((prev) => ({ ...prev, when_to_use: e.target.value }))}
        rows={3}
        disabled={disabled}
        placeholder="e.g., Use when the user asks to generate or edit a Word document."
        helpText="Extra routing guidance for the skill selector — kept separate from the description."
      />

      <FormTextArea
        label="Skill Instructions"
        id="content"
        value={formState.content}
        onChange={(e) => setFormState((prev) => ({ ...prev, content: e.target.value }))}
        rows={12}
        disabled={disabled}
        required
        textareaClassName="font-mono text-sm"
        helpText="Markdown-formatted instructions loaded when the agent activates this skill."
      />

      <div>
        <label
          htmlFor={disabled ? undefined : 'allowed_tools'}
          className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2"
        >
          Allowed Tools
        </label>
        <AllowedToolsInput
          tools={formState.allowed_tools}
          onChange={(tools) => setFormState((prev) => ({ ...prev, allowed_tools: tools }))}
          disabled={disabled}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <FormField
          label="Runtime"
          id="runtime"
          value={formState.runtime}
          onChange={(e) => setFormState((prev) => ({ ...prev, runtime: e.target.value }))}
          placeholder="e.g., python3.11"
          disabled={disabled}
          helpText="Sandbox runtime this skill expects, if any."
        />

        <FormField
          label="Bootstrap Script Path"
          id="bootstrap_script_path"
          value={formState.bootstrap_script_path}
          onChange={(e) => setFormState((prev) => ({ ...prev, bootstrap_script_path: e.target.value }))}
          placeholder="scripts/bootstrap.sh"
          disabled={disabled}
          inputClassName="font-mono text-sm"
          helpText="Package-root-relative path to a script that runs after resources are copied into the sandbox."
        />
      </div>

      <div>
        <label htmlFor="runtime_options" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Runtime Options (JSON)
        </label>
        <textarea
          id="runtime_options"
          name="runtime_options"
          value={formState.runtime_options_text}
          onChange={(e) => setFormState((prev) => ({ ...prev, runtime_options_text: e.target.value }))}
          disabled={disabled}
          rows={6}
          aria-invalid={!runtimeOptionsValidation.valid}
          aria-describedby="runtime_options_help"
          placeholder={'{\n  "pip_packages": ["pandas"]\n}'}
          className={`w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 transition-colors font-mono text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 ${
            !runtimeOptionsValidation.valid
              ? 'border-red-300 dark:border-red-600 focus:ring-red-500 focus:border-red-500'
              : 'border-gray-300 dark:border-gray-600 focus:ring-purple-500 focus:border-purple-500'
          } ${disabled ? 'bg-gray-100 dark:bg-gray-900 cursor-not-allowed' : ''}`}
        />
        {'error' in runtimeOptionsValidation ? (
          <p id="runtime_options_help" className="mt-1 flex items-start gap-1 text-xs text-red-600 dark:text-red-400">
            <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" aria-hidden="true" />
            <span>{runtimeOptionsValidation.error}</span>
          </p>
        ) : (
          <p id="runtime_options_help" className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Optional JSON object passed to the sandbox runtime. Leave blank for none.
          </p>
        )}
      </div>

      <FormCheckbox
        label="Enabled"
        id="is_enabled"
        checked={formState.is_enabled}
        onChange={(e) => setFormState((prev) => ({ ...prev, is_enabled: e.target.checked }))}
        disabled={disabled}
        helpText="Disabled skills are ignored at execution time until re-enabled."
      />

      {isEditing && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="block text-sm font-medium text-gray-700 dark:text-gray-300">Package Resources</span>
            <span className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
              {skill?.is_system && <Badge label="System" variant="secondary" />}
              {skill?.is_enabled === false && <Badge label="Disabled" variant="warning" />}
              {files.length === 0 ? 'SKILL.md only' : `${files.length} bundled ${files.length === 1 ? 'file' : 'files'}`}
            </span>
          </div>
          <div className="border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 overflow-hidden">
            <div className="flex items-center gap-2 border-b border-gray-100 dark:border-gray-700 px-3 py-2 text-sm text-gray-700 dark:text-gray-200 bg-gray-50 dark:bg-gray-900">
              <FileText className="w-4 h-4 shrink-0 text-purple-500" aria-hidden="true" />
              <span className="font-mono text-xs">SKILL.md</span>
              <span className="ml-auto text-xs text-gray-400">instructions</span>
            </div>
            {fileTree.length > 0 ? (
              <div className="max-h-72 overflow-y-auto py-1">
                <FileTreeView
                  nodes={fileTree}
                  expandedFolders={expandedFolders}
                  onToggleFolder={handleToggleFolder}
                  expandedFiles={expandedFiles}
                  previews={previews}
                  onToggleFile={handleToggleFile}
                />
              </div>
            ) : (
              <p className="px-3 py-4 text-sm text-gray-500 dark:text-gray-400">
                This skill does not include bundled resources.
              </p>
            )}
          </div>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Read-only. Text file previews are fetched only when a file is expanded.
          </p>
        </div>
      )}

      {isReadOnly ? (
        <div className="flex justify-end pt-4 border-t border-gray-200 dark:border-gray-700">
          <button
            type="button"
            onClick={onCancel}
            className="px-4 py-2 text-gray-700 dark:text-gray-200 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      ) : (
        <FormActions
          onCancel={onCancel}
          isSubmitting={isSubmitting}
          isEditing={isEditing}
          submitLabel={isEditing ? 'Update Skill' : 'Create Skill'}
          submitButtonColor="purple"
          disabled={!isValid}
        />
      )}
    </form>
  );
}

export default SkillForm;
