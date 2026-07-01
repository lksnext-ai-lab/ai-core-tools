import { useState, useEffect, useRef } from 'react';
import { AlertTriangle, Trash2, ArrowRightLeft, Loader2 } from 'lucide-react';
import Modal from '../ui/Modal';
import UserPicker from '../ui/UserPicker';
import { adminService } from '../../services/admin';
import type { User } from '../../services/admin';
import { errorMessage } from '../../constants/messages';

type DialogBranch = 'choose' | 'transfer' | 'cascade';

export interface DeleteUserDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  /** The user about to be deleted — must have owned_apps_count > 0. */
  readonly targetUser: User;
  /** Called after the delete operation succeeds so the parent can refresh. */
  readonly onDeleted: () => void;
}

const CASCADE_CONFIRM_PHRASE = 'delete all apps';

const TRANSFER_PICKER_ID = 'delete-dialog-transfer-section';
const CASCADE_INPUT_ID = 'cascade-confirm-input';
const CASCADE_ERROR_ID = 'cascade-confirm-error';

function DeleteUserDialog({
  isOpen,
  onClose,
  targetUser,
  onDeleted,
}: Readonly<DeleteUserDialogProps>) {
  const [branch, setBranch] = useState<DialogBranch>('choose');
  const [transferTarget, setTransferTarget] = useState<User | null>(null);
  const [cascadeConfirm, setCascadeConfirm] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const transferFocusRef = useRef<HTMLDivElement>(null);
  const cascadeFocusRef = useRef<HTMLDivElement>(null);

  const targetLabel = targetUser.name || targetUser.email;
  const appCount = targetUser.owned_apps_count;
  const appWord = appCount === 1 ? 'app' : 'apps';

  // Focus the entry point of each branch on transition; Modal handles 'choose' initial focus.
  useEffect(() => {
    if (branch === 'transfer') {
      transferFocusRef.current?.focus();
    } else if (branch === 'cascade') {
      cascadeFocusRef.current?.focus();
    }
  }, [branch]);

  function handleClose() {
    if (isSubmitting) return;
    setBranch('choose');
    setTransferTarget(null);
    setCascadeConfirm('');
    setSubmitError(null);
    onClose();
  }

  async function handleTransferAndDelete() {
    if (!transferTarget) return;
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await adminService.deleteUser(targetUser.user_id, {
        mode: 'transfer_apps',
        transferToUserId: transferTarget.user_id,
      });
      handleClose();
      onDeleted();
    } catch (err: unknown) {
      setSubmitError(errorMessage(err, 'Failed to delete user'));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCascadeDelete() {
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await adminService.deleteUser(targetUser.user_id, { mode: 'cascade_apps' });
      handleClose();
      onDeleted();
    } catch (err: unknown) {
      setSubmitError(errorMessage(err, 'Failed to delete user'));
    } finally {
      setIsSubmitting(false);
    }
  }

  const cascadeConfirmPhraseMatches =
    cascadeConfirm.trim().toLowerCase() === CASCADE_CONFIRM_PHRASE;

  const showCascadeInputError = cascadeConfirm.length > 0 && !cascadeConfirmPhraseMatches;

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={`Delete user: ${targetLabel}`}
      size="medium"
    >
      <div className="space-y-5">
        <div className="flex gap-3 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg">
          <AlertTriangle
            className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5"
            aria-hidden="true"
          />
          <div className="text-sm text-amber-800 dark:text-amber-200">
            <strong className="text-amber-800 dark:text-amber-200">{targetLabel}</strong> owns{' '}
            <strong className="text-amber-800 dark:text-amber-200">
              {appCount} {appWord}
            </strong>
            . Choose what to do with their {appWord} before deleting this account.
          </div>
        </div>

        {submitError && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-lg px-4 py-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800"
          >
            <AlertTriangle
              className="w-4 h-4 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5"
              aria-hidden="true"
            />
            <p className="text-sm text-red-700 dark:text-red-300">{submitError}</p>
          </div>
        )}

        {branch === 'choose' && (
          <div className="space-y-3">
            <p className="text-sm font-medium text-gray-700 dark:text-slate-300">
              Choose an option:
            </p>

            <button
              type="button"
              onClick={() => setBranch('transfer')}
              className="w-full flex items-start gap-4 p-4 text-left border border-gray-200 dark:border-slate-600 rounded-lg hover:border-blue-400 dark:hover:border-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
            >
              <ArrowRightLeft
                className="w-5 h-5 text-blue-600 dark:text-blue-400 flex-shrink-0 mt-0.5"
                aria-hidden="true"
              />
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-slate-100">
                  Transfer {appWord} to another user
                </p>
                <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5">
                  Reassign ownership of all {appCount} {appWord} to a user you choose, then
                  delete this account.
                </p>
              </div>
            </button>

            <button
              type="button"
              onClick={() => setBranch('cascade')}
              className="w-full flex items-start gap-4 p-4 text-left border border-gray-200 dark:border-slate-600 rounded-lg hover:border-red-400 dark:hover:border-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 focus:outline-none focus:ring-2 focus:ring-red-500 transition-colors"
            >
              <Trash2
                className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5"
                aria-hidden="true"
              />
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-slate-100">
                  Delete user and all their {appWord}
                </p>
                <p className="text-xs text-gray-500 dark:text-slate-400 mt-0.5">
                  Permanently delete all {appCount} {appWord} and all their data (agents,
                  silos, vector collections). This cannot be undone.
                </p>
              </div>
            </button>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={handleClose}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {branch === 'transfer' && (
          <div className="space-y-4">
            {/* tabIndex={-1} allows programmatic focus on branch entry without disrupting UserPicker focus */}
            <div
              ref={transferFocusRef}
              id={TRANSFER_PICKER_ID}
              tabIndex={-1}
              className="focus:outline-none"
            >
              <UserPicker
                label={`Transfer ${appWord} to`}
                value={transferTarget}
                onSelect={setTransferTarget}
                onClear={() => setTransferTarget(null)}
                excludeUserId={targetUser.user_id}
                disabled={isSubmitting}
                inputId="delete-dialog-user-picker"
              />
            </div>

            {transferTarget && (
              <p className="text-sm text-gray-600 dark:text-slate-400">
                All {appCount} {appWord} owned by{' '}
                <strong className="text-gray-900 dark:text-slate-100">{targetLabel}</strong> will
                be transferred to{' '}
                <strong className="text-gray-900 dark:text-slate-100">
                  {transferTarget.name || transferTarget.email}
                </strong>
                , then the account will be permanently deleted.
              </p>
            )}

            <div className="flex justify-end gap-3 border-t border-gray-200 dark:border-slate-700 pt-4">
              <button
                type="button"
                aria-label="Back to options"
                onClick={() => {
                  setBranch('choose');
                  setTransferTarget(null);
                  setSubmitError(null);
                }}
                disabled={isSubmitting}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 transition-colors"
              >
                Back
              </button>
              <button
                type="button"
                onClick={() => { void handleTransferAndDelete(); }}
                disabled={!transferTarget || isSubmitting}
                aria-busy={isSubmitting}
                aria-describedby={!transferTarget ? TRANSFER_PICKER_ID : undefined}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isSubmitting && (
                  <Loader2 className="animate-spin w-4 h-4" aria-hidden="true" />
                )}
                {isSubmitting ? 'Transferring…' : `Transfer ${appWord} and delete user`}
              </button>
            </div>
          </div>
        )}

        {branch === 'cascade' && (
          <div className="space-y-4">
            {/* tabIndex={-1} allows programmatic focus on branch entry; dark:border-red-600 meets 3:1 non-text contrast */}
            <div
              ref={cascadeFocusRef}
              tabIndex={-1}
              className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-600 rounded-lg space-y-2 focus:outline-none"
            >
              <p className="text-sm font-semibold text-red-800 dark:text-red-200">
                This will permanently delete:
              </p>
              <ul className="text-sm text-red-700 dark:text-red-300 list-disc list-inside space-y-0.5">
                <li>
                  All {appCount} {appWord} owned by {targetLabel}
                </li>
                <li>All agents, silos, vector collections, and API keys in those {appWord}</li>
                <li>The user account itself</li>
              </ul>
              <p className="text-sm text-red-800 dark:text-red-200 font-medium mt-2">
                This action cannot be undone.
              </p>
            </div>

            <div>
              <label
                htmlFor={CASCADE_INPUT_ID}
                className="block text-sm font-medium text-gray-700 dark:text-slate-300 mb-1.5"
              >
                Type{' '}
                <code className="px-1 py-0.5 bg-gray-100 dark:bg-slate-700 rounded text-xs font-mono text-gray-800 dark:text-slate-200">
                  {CASCADE_CONFIRM_PHRASE}
                </code>{' '}
                to confirm:
              </label>
              <input
                id={CASCADE_INPUT_ID}
                type="text"
                value={cascadeConfirm}
                onChange={(e) => setCascadeConfirm(e.target.value)}
                disabled={isSubmitting}
                aria-required="true"
                aria-invalid={showCascadeInputError}
                aria-describedby={showCascadeInputError ? CASCADE_ERROR_ID : undefined}
                placeholder={CASCADE_CONFIRM_PHRASE}
                className="w-full px-3 py-2 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-lg text-sm text-gray-900 dark:text-slate-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent disabled:opacity-50 disabled:cursor-not-allowed"
              />
              {showCascadeInputError && (
                <p
                  id={CASCADE_ERROR_ID}
                  role="alert"
                  className="mt-1 text-xs text-red-600 dark:text-red-400"
                >
                  Type exactly: {CASCADE_CONFIRM_PHRASE}
                </p>
              )}
            </div>

            <div className="flex justify-end gap-3 border-t border-gray-200 dark:border-slate-700 pt-4">
              <button
                type="button"
                aria-label="Back to options"
                onClick={() => {
                  setBranch('choose');
                  setCascadeConfirm('');
                  setSubmitError(null);
                }}
                disabled={isSubmitting}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-slate-300 bg-white dark:bg-slate-700 border border-gray-300 dark:border-slate-600 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 transition-colors"
              >
                Back
              </button>
              <button
                type="button"
                onClick={() => { void handleCascadeDelete(); }}
                disabled={!cascadeConfirmPhraseMatches || isSubmitting}
                aria-busy={isSubmitting}
                aria-describedby={CASCADE_INPUT_ID}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isSubmitting && (
                  <Loader2 className="animate-spin w-4 h-4" aria-hidden="true" />
                )}
                {isSubmitting ? 'Deleting…' : `Delete user and all ${appWord}`}
              </button>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

export default DeleteUserDialog;
