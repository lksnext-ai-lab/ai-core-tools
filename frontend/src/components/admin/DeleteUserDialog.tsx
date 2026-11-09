import { useState, useEffect, useRef } from 'react';
import { Trash2, ArrowRightLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Modal from '../ui/Modal';
import Alert from '../ui/Alert';
import { ButtonCard } from '../ui/ButtonCard';
import { ButtonApp } from '../ui/ButtonApp';
import FormField from '../ui/FormField';
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

const TRANSFER_PICKER_ID = 'delete-dialog-transfer-section';
const CASCADE_INPUT_ID = 'cascade-confirm-input';
const CASCADE_ERROR_ID = 'cascade-confirm-error';

function DeleteUserDialog({
  isOpen,
  onClose,
  targetUser,
  onDeleted,
}: Readonly<DeleteUserDialogProps>) {
  const { t } = useTranslation('common');
  const [branch, setBranch] = useState<DialogBranch>('choose');
  const [transferTarget, setTransferTarget] = useState<User | null>(null);
  const [cascadeConfirm, setCascadeConfirm] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const transferFocusRef = useRef<HTMLDivElement>(null);
  const cascadeFocusRef = useRef<HTMLDivElement>(null);

  const targetLabel = targetUser.name || targetUser.email;
  const appCount = targetUser.owned_apps_count;
  const appWord = t('deleteUserDialog.app', { count: appCount });
  const cascadeConfirmPhrase = t('deleteUserDialog.cascadeConfirmPhrase');

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
      setSubmitError(errorMessage(err, t('userManagement.deleteFailed')));
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
      setSubmitError(errorMessage(err, t('userManagement.deleteFailed')));
    } finally {
      setIsSubmitting(false);
    }
  }

  const cascadeConfirmPhraseMatches =
    cascadeConfirm.trim().toLowerCase() === cascadeConfirmPhrase.toLowerCase();

  const showCascadeInputError = cascadeConfirm.length > 0 && !cascadeConfirmPhraseMatches;

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={t('deleteUserDialog.title', { name: targetLabel })}
      size="medium"
    >
      <div className="space-y-5">
        <Alert
          type="warning"
          message={(
            <>
              <strong>{targetLabel}</strong> {t('deleteUserDialog.owns')}{' '}
              <strong>{appCount} {appWord}</strong>.{' '}
              {t('deleteUserDialog.chooseWhatToDo', { app: appWord })}
            </>
          )}
        />

        {submitError && <Alert type="error" message={submitError} />}

        {branch === 'choose' && (
          <div className="space-y-3">
            <p className="text-sm font-medium text-gray-700 dark:text-slate-300">
              {t('deleteUserDialog.chooseOption')}
            </p>

            <ButtonCard
              variant="selectable"
              className="w-full"
              ariaLabel={t('deleteUserDialog.transferApps', { app: appWord })}
              onClick={() => setBranch('transfer')}
            >
              <div className="flex items-start gap-4">
                <ArrowRightLeft
                  className="w-5 h-5 text-fg dark:text-fg-dark flex-shrink-0 mt-0.5"
                  aria-hidden="true"
                />
                <div>
                  <p className="text-sm font-semibold text-fg dark:text-fg-dark">
                    {t('deleteUserDialog.transferApps', { app: appWord })}
                  </p>
                  <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark mt-0.5">
                    {t('deleteUserDialog.transferDescription', { count: appCount, app: appWord })}
                  </p>
                </div>
              </div>
            </ButtonCard>

            <ButtonCard
              variant="selectable"
              className="w-full"
              ariaLabel={t('deleteUserDialog.deleteUserAndApps', { app: appWord })}
              onClick={() => setBranch('cascade')}
            >
              <div className="flex items-start gap-4">
                <Trash2
                  className="w-5 h-5 text-fg dark:text-fg-dark flex-shrink-0 mt-0.5"
                  aria-hidden="true"
                />
                <div>
                  <p className="text-sm font-semibold text-fg dark:text-fg-dark">
                    {t('deleteUserDialog.deleteUserAndApps', { app: appWord })}
                  </p>
                  <p className="text-xs text-fg-secondary dark:text-fg-secondary-dark mt-0.5">
                    {t('deleteUserDialog.cascadeDescription', { count: appCount, app: appWord })}
                  </p>
                </div>
              </div>
            </ButtonCard>

            <div className="flex justify-end pt-2">
              <ButtonApp
                label={t('cancel')}
                variant="secondary"
                size="medium"
                onClick={handleClose}
              />
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
                label={t('deleteUserDialog.transferAppsTo')}
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
                {t('deleteUserDialog.transferConfirmation', {
                  count: appCount,
                  app: appWord,
                  name: targetLabel,
                  transferName: transferTarget.name || transferTarget.email,
                })}
              </p>
            )}

            <div className="flex justify-end gap-3 border-t border-gray-200 dark:border-slate-700 pt-4">
              <ButtonApp
                label={t('deleteUserDialog.back')}
                ariaLabel={t('deleteUserDialog.backToOptions')}
                variant="secondary"
                size="medium"
                onClick={() => {
                  setBranch('choose');
                  setTransferTarget(null);
                  setSubmitError(null);
                }}
                disabled={isSubmitting}
              />
              <ButtonApp
                label={isSubmitting
                  ? t('deleteUserDialog.transferring')
                  : t('deleteUserDialog.transferAndDelete', { app: appWord })}
                onClick={() => { void handleTransferAndDelete(); }}
                disabled={!transferTarget}
                loading={isSubmitting}
                ariaDescribedBy={!transferTarget ? TRANSFER_PICKER_ID : undefined}
                variant="dangerSolid"
                size="medium"
              />
            </div>
          </div>
        )}

        {branch === 'cascade' && (
          <div className="space-y-4">
            <div
              ref={cascadeFocusRef}
              tabIndex={-1}
              className="focus:outline-none"
            >
              <Alert
                type="info"
                message={(
                  <>
                    <p className="font-medium">{t('deleteUserDialog.permanentlyDelete')}</p>
                    <ul className="mt-1 list-inside list-disc space-y-0.5">
                      <li>
                        {t('deleteUserDialog.appsOwnedBy', {
                          count: appCount,
                          app: appWord,
                          name: targetLabel,
                        })}
                      </li>
                      <li>{t('deleteUserDialog.resourcesInApps', { app: appWord })}</li>
                      <li>{t('deleteUserDialog.userAccount')}</li>
                    </ul>
                    <p className="mt-2 font-medium">{t('deleteUserDialog.cannotUndo')}</p>
                  </>
                )}
              />
            </div>

            <div>
              <label
                htmlFor={CASCADE_INPUT_ID}
                className="block text-sm font-medium text-fg dark:text-fg-dark mb-1.5"
              >
                {t('deleteUserDialog.typeToConfirm')}{' '}
                <code className="px-1 py-0.5 bg-canvas-alt dark:bg-canvas-alt-dark rounded text-xs font-mono text-fg-secondary dark:text-fg-secondary-dark">
                  {cascadeConfirmPhrase}
                </code>{' '}
                {t('deleteUserDialog.confirmSuffix')}
              </label>
              <FormField
                id={CASCADE_INPUT_ID}
                type="text"
                value={cascadeConfirm}
                onChange={(e) => setCascadeConfirm(e.target.value)}
                disabled={isSubmitting}
                ariaRequired
                ariaInvalid={showCascadeInputError}
                ariaDescribedBy={showCascadeInputError ? CASCADE_ERROR_ID : undefined}
                placeholder={cascadeConfirmPhrase}
                inputClassName={showCascadeInputError
                  ? 'border-error focus:border-error dark:border-error-dark dark:focus:border-error-dark'
                  : ''}
              />
              {showCascadeInputError && (
                <p
                  id={CASCADE_ERROR_ID}
                  role="alert"
                  className="mt-1 text-xs text-error dark:text-error-dark"
                >
                  {t('deleteUserDialog.typeExactly', { phrase: cascadeConfirmPhrase })}
                </p>
              )}
            </div>

            <div className="flex justify-end gap-3 border-t border-gray-200 dark:border-slate-700 pt-4">
              <ButtonApp
                label={t('deleteUserDialog.back')}
                ariaLabel={t('deleteUserDialog.backToOptions')}
                variant="secondary"
                size="medium"
                onClick={() => {
                  setBranch('choose');
                  setCascadeConfirm('');
                  setSubmitError(null);
                }}
                disabled={isSubmitting}
              />
              <ButtonApp
                label={isSubmitting
                  ? t('deleteUserDialog.deleting')
                  : t('deleteUserDialog.deleteUserAndApps', { app: appWord })}
                variant="dangerSolid"
                size="medium"
                onClick={() => { void handleCascadeDelete(); }}
                disabled={!cascadeConfirmPhraseMatches}
                loading={isSubmitting}
                ariaDescribedBy={CASCADE_INPUT_ID}
              />
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
}

export default DeleteUserDialog;
