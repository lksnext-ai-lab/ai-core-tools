import React, { useState, useRef } from 'react';
import { Download, FileText } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { apiService } from '../../services/api';
import MessageContent from './MessageContent';
import { ButtonApp } from '../ui/ButtonApp';
import ActionDropdown from '../ui/ActionDropdown';
import { SegmentedTabs } from '../ui/SegmentedTabs';
import { SidePanel } from '../ui/SidePanel';
import { useConfirm } from '../../contexts/ConfirmContext';

interface OCRInterfaceProps {
  appId: number;
  agentId: number;
  agentName: string;
  outputParser?: {
    parser_id: number;
    name: string;
    description?: string;
    fields: Array<{
      name: string;
      type: string;
      description: string;
      optional?: boolean;
    }>;
  };
  onError?: (message: string) => void;
}

interface OCRResult {
  id: string;
  timestamp: Date;
  originalFile: File;
  extractedText: string;
  metadata?: any;
  result?: any; // For structured results from output parsers
}

type ResultTab = 'data' | 'text' | 'meta';

/** List id of the file chosen but not processed yet. */
const PENDING_ID = 'pending';

export const OCRInterface: React.FC<OCRInterfaceProps> = ({
  appId,
  agentId,
  outputParser,
  onError
}) => {
  const { t, i18n } = useTranslation('common');
  const confirm = useConfirm();
  const [results, setResults] = useState<OCRResult[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const [isFieldsPanelOpen, setIsFieldsPanelOpen] = useState(false);
  const [selectedResultId, setSelectedResultId] = useState<string | null>(null);
  const [activeResultTab, setActiveResultTab] = useState<ResultTab>('data');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      setSelectedResultId(PENDING_ID);

      // Create preview URL for PDF files
      if (file.type === 'application/pdf') {
        const url = URL.createObjectURL(file);
        setPdfPreviewUrl(url);
      } else {
        setPdfPreviewUrl(null);
      }
    }
  };

  const handleProcessOCR = async () => {
    if (!selectedFile) return;

    setIsProcessing(true);

    try {
      const response = await apiService.processOCR(appId, agentId, selectedFile);

      const result: OCRResult = {
        id: Date.now().toString(),
        timestamp: new Date(),
        originalFile: selectedFile,
        extractedText: response.extracted_text || t('playgroundOcr.noTextExtracted'),
        metadata: response.metadata,
        result: response.result // For structured results
      };

      setResults(prev => [result, ...prev]);
      setSelectedResultId(result.id);
      setActiveResultTab('data');
      setSelectedFile(null);
      setPdfPreviewUrl(null);

      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (error) {
      console.error('OCR processing error:', error);
      onError?.(error instanceof Error ? error.message : t('playgroundOcr.processFailed'));
    } finally {
      setIsProcessing(false);
    }
  };

  const handleClearResults = () => {
    setResults([]);
  };

  const handleConfirmClearResults = async () => {
    const ok = await confirm({
      title: t('playgroundOcr.clearConfirmTitle'),
      message: t('playgroundOcr.clearConfirmMessage', { count: results.length }),
      confirmLabel: t('playgroundOcr.clearResults'),
      cancelLabel: t('cancel'),
      variant: 'danger',
    });
    if (ok) handleClearResults();
  };

  const downloadResult = (result: OCRResult) => {
    // If we have structured content, download that; otherwise download extracted text
    const content = result.result?.content
      ? JSON.stringify(result.result.content, null, 2)
      : result.extractedText;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${result.originalFile.name.replace(/\.[^/.]+$/, '')}_${t('playgroundOcr.resultFileSuffix')}.txt`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  const openFilePicker = () => fileInputRef.current?.click();
  const formatDate = (date: Date) => date.toLocaleString(i18n.resolvedLanguage ?? i18n.language);

  const hasResults = results.length > 0;
  const isEmpty = !hasResults && !selectedFile;
  const isPendingSelected = !!selectedFile && (selectedResultId === PENDING_ID || !hasResults);
  const selectedResult = isPendingSelected
    ? undefined
    : results.find(r => r.id === selectedResultId) ?? results[0];
  const formatFileSize = (bytes: number) => {
    const locale = i18n.resolvedLanguage ?? i18n.language;
    if (bytes >= 1024 * 1024) {
      return `${(bytes / (1024 * 1024)).toLocaleString(locale, { maximumFractionDigits: 1 })} MB`;
    }
    return `${Math.max(1, Math.round(bytes / 1024)).toLocaleString(locale)} KB`;
  };
  const listItemClass = (isCurrent: boolean) =>
    `flex w-full flex-col gap-[3px] rounded-md border-l-2 px-3 py-2.5 text-left text-fg transition-colors hover:bg-surface-hover dark:text-fg-dark dark:hover:bg-surface-hover-dark ${
      isCurrent
        ? 'border-accent bg-surface-hover dark:border-accent-dark dark:bg-surface-hover-dark'
        : 'border-transparent'
    }`;

  const resultTabs: Array<{ id: ResultTab; label: string }> = [];
  if (selectedResult?.result?.content) resultTabs.push({ id: 'data', label: t('playgroundOcr.tabData') });
  if (selectedResult?.extractedText) resultTabs.push({ id: 'text', label: t('playgroundOcr.tabText') });
  if (selectedResult?.metadata) resultTabs.push({ id: 'meta', label: t('playgroundOcr.tabMeta') });
  const currentTab = resultTabs.some(tab => tab.id === activeResultTab) ? activeResultTab : resultTabs[0]?.id;

  return (
    <div className="pt-4">
      <p className="mb-3.5 max-w-[680px] text-sm text-fg-secondary dark:text-fg-secondary-dark">
        {t('playgroundOcr.description')}
      </p>

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf"
        onChange={handleFileSelect}
        className="hidden"
      />

      {/* Toolbar: output format (read-only) + documents summary and actions */}
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 border-b border-line bg-surface py-3 dark:border-line-dark dark:bg-surface-dark">
        {outputParser ? (
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm">
            <span className="font-medium text-fg dark:text-fg-dark">{t('playgroundOcr.outputFormatLabel')}</span>
            <span className="text-fg-secondary dark:text-fg-secondary-dark">{outputParser.name}</span>
            <button
              type="button"
              aria-haspopup="dialog"
              aria-expanded={isFieldsPanelOpen}
              onClick={() => setIsFieldsPanelOpen(true)}
              className="text-sm text-fg underline decoration-line-strong underline-offset-4 transition-colors hover:decoration-accent dark:text-fg-dark dark:decoration-line-strong-dark dark:hover:decoration-accent-dark"
            >
              {t('playgroundOcr.viewFields')}
            </button>
          </div>
        ) : (
          <span />
        )}
        <div className="flex flex-wrap items-center gap-2.5">
          <span role="status" className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
            {hasResults ? t('playgroundOcr.summary', { count: results.length }) : t('playgroundOcr.summaryEmpty')}
          </span>
          {!isEmpty && (
            <>
              <ButtonApp label={t('playgroundOcr.addPdf')} onClick={openFilePicker} variant="secondary" size="small" />
              {hasResults && (
                <ActionDropdown
                  triggerText={t('playgroundOcr.actions')}
                  triggerIcon={null}
                  triggerAriaLabel={t('playgroundOcr.actionsAria')}
                  size="sm"
                  actions={[
                    { label: t('playgroundOcr.clearResults'), onClick: handleConfirmClearResults, variant: 'danger' },
                  ]}
                />
              )}
            </>
          )}
        </div>
      </div>

      {/* Empty state */}
      {isEmpty && (
        <div className="flex flex-col items-center rounded-lg border border-dashed border-line-strong px-6 py-12 text-center dark:border-line-strong-dark">
          <span className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-surface-hover text-fg-secondary dark:bg-surface-hover-dark dark:text-fg-secondary-dark">
            <FileText className="h-[18px] w-[18px]" aria-hidden="true" />
          </span>
          <h2 className="mb-1 font-display text-base font-normal tracking-[-0.02em] text-fg dark:text-fg-dark">
            {t('playgroundOcr.emptyTitle')}
          </h2>
          <p className="mb-4 max-w-md text-sm text-fg-secondary dark:text-fg-secondary-dark">
            {outputParser
              ? t('playgroundOcr.emptyTextWithFormat', { name: outputParser.name })
              : t('playgroundOcr.emptyText')}
          </p>
          <ButtonApp label={t('playgroundOcr.addPdf')} onClick={openFilePicker} size="medium" />
        </div>
      )}

      {/* Documents: list (pending + processed) + selected document */}
      {!isEmpty && (
        <div className="grid grid-cols-1 items-start gap-[22px] lg:grid-cols-[300px_minmax(0,1fr)]">
          <nav
            aria-label={t('playgroundOcr.documentsNav')}
            className="rounded-lg border border-line bg-surface-tint dark:border-line-dark dark:bg-surface-tint-dark"
          >
            <ul className="flex flex-col gap-0.5 p-1.5">
              {selectedFile && (
                <li>
                  <button
                    type="button"
                    aria-current={isPendingSelected ? 'true' : undefined}
                    onClick={() => setSelectedResultId(PENDING_ID)}
                    className={listItemClass(isPendingSelected)}
                  >
                    <span className="text-[13.5px] font-medium [overflow-wrap:anywhere]">{selectedFile.name}</span>
                    <span className="text-[11.5px] text-fg-tertiary dark:text-fg-tertiary-dark">{formatFileSize(selectedFile.size)}</span>
                    <span
                      className={`self-start rounded-full px-2 py-0.5 text-[11px] font-medium ${
                        isProcessing
                          ? 'bg-info-bg text-info dark:bg-info-bg-dark dark:text-info-dark'
                          : 'bg-surface text-fg-secondary dark:bg-surface-dark dark:text-fg-secondary-dark'
                      }`}
                    >
                      {isProcessing ? t('playgroundOcr.processing') : t('playgroundOcr.statusPending')}
                    </span>
                  </button>
                </li>
              )}
              {results.map((result) => {
                const isCurrent = result.id === selectedResult?.id;
                return (
                  <li key={result.id}>
                    <button
                      type="button"
                      aria-current={isCurrent ? 'true' : undefined}
                      onClick={() => setSelectedResultId(result.id)}
                      className={listItemClass(isCurrent)}
                    >
                      <span className="text-[13.5px] font-medium [overflow-wrap:anywhere]">{result.originalFile.name}</span>
                      <span className="text-[11.5px] text-fg-tertiary dark:text-fg-tertiary-dark">{formatDate(result.timestamp)}</span>
                      <span className="self-start rounded-full bg-success-bg px-2 py-0.5 text-[11px] font-medium text-success-strong dark:bg-success-bg-dark dark:text-success-strong-dark">
                        {t('playgroundOcr.statusDone')}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>

          {selectedFile && isPendingSelected && (
            <section aria-label={selectedFile.name} className="min-w-0">
              <div className="mb-4 min-w-0">
                <h2 className="mb-1 font-display text-xl font-normal tracking-[-0.02em] text-fg [overflow-wrap:anywhere] dark:text-fg-dark">
                  {selectedFile.name}
                </h2>
                <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">{formatFileSize(selectedFile.size)}</p>
              </div>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-line bg-surface-tint px-4 py-3 dark:border-line-dark dark:bg-surface-tint-dark">
                <p role="status" className="text-sm text-fg-secondary dark:text-fg-secondary-dark">
                  {isProcessing ? t('playgroundOcr.processingText') : t('playgroundOcr.pendingText')}
                </p>
                <ButtonApp
                  label={isProcessing ? t('playgroundOcr.processing') : t('playgroundOcr.processThis')}
                  onClick={handleProcessOCR}
                  loading={isProcessing}
                  size="medium"
                />
              </div>
              {pdfPreviewUrl && (
                <div className="max-w-[620px] overflow-hidden rounded-lg border border-line dark:border-line-dark">
                  <iframe
                    src={pdfPreviewUrl}
                    className="h-96 w-full"
                    title={t('playgroundOcr.preview')}
                  />
                </div>
              )}
            </section>
          )}

          {selectedResult && (
          <section aria-label={selectedResult.originalFile.name} className="min-w-0">
            <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="mb-1 font-display text-xl font-normal tracking-[-0.02em] text-fg [overflow-wrap:anywhere] dark:text-fg-dark">
                  {selectedResult.originalFile.name}
                </h2>
                <p className="text-xs text-fg-tertiary dark:text-fg-tertiary-dark">
                  {t('playgroundOcr.processedMeta', { date: formatDate(selectedResult.timestamp) })}
                  {outputParser && ` · ${t('playgroundOcr.formatMeta', { name: outputParser.name })}`}
                </p>
              </div>
              <ButtonApp
                label={t('playgroundOcr.download')}
                icon={<Download className="h-4 w-4" />}
                onClick={() => downloadResult(selectedResult)}
                variant="secondary"
                size="medium"
              />
            </div>

            {resultTabs.length > 1 && currentTab && (
              <SegmentedTabs
                tabs={resultTabs}
                activeTab={currentTab}
                onChange={setActiveResultTab}
                ariaLabel={t('playgroundOcr.resultTabsAria')}
                className="mb-4 sm:w-auto sm:max-w-[520px]"
              />
            )}

            {currentTab === 'data' && (
              <div className="rounded-lg border border-line bg-surface dark:border-line-dark dark:bg-surface-dark">
                <MessageContent content={selectedResult.result.content} />
              </div>
            )}

            {currentTab === 'text' && (
              <div className="rounded-lg border border-line bg-surface-tint dark:border-line-dark dark:bg-surface-tint-dark">
                <pre className="whitespace-pre-wrap p-4 font-sans text-sm leading-relaxed text-fg dark:text-fg-dark">
                  {selectedResult.extractedText}
                </pre>
              </div>
            )}

            {currentTab === 'meta' && (
              <div className="rounded-lg border border-line bg-surface-tint dark:border-line-dark dark:bg-surface-tint-dark">
                <pre className="whitespace-pre-wrap p-4 text-[13px] text-fg dark:text-fg-dark">
                  {JSON.stringify(selectedResult.metadata, null, 2)}
                </pre>
              </div>
            )}
          </section>
          )}
        </div>
      )}

      {/* Output format fields (read-only) */}
      {outputParser && (
        <SidePanel
          open={isFieldsPanelOpen}
          onClose={() => setIsFieldsPanelOpen(false)}
          side="right"
          title={t('playgroundOcr.outputFormatLabel')}
          closeLabel={t('playgroundOcr.closePanel')}
          widthClassName="w-[480px] max-w-full"
        >
          <div className="px-3 pt-3">
            <h3 className="mb-1 font-display text-xl font-normal tracking-[-0.02em] text-fg dark:text-fg-dark">
              {outputParser.name}
            </h3>
            {outputParser.description && (
              <p className="mb-4 text-sm text-fg-secondary dark:text-fg-secondary-dark">{outputParser.description}</p>
            )}
            {outputParser.fields && outputParser.fields.length > 0 && (
              <>
                <h4 className="mb-2 text-xs font-medium text-fg-tertiary dark:text-fg-tertiary-dark">
                  {t('playgroundOcr.outputFields')}
                </h4>
                <ul className="flex flex-col gap-2">
                  {outputParser.fields.map((field) => (
                    <li key={field.name} className="rounded-md bg-surface-hover px-3.5 py-3 dark:bg-surface-hover-dark">
                      <div className="text-[13px] font-medium text-fg dark:text-fg-dark">
                        {field.name}
                        {field.optional && (
                          <span className="ml-1 font-normal italic text-fg-tertiary dark:text-fg-tertiary-dark">({t('playgroundOcr.optional')})</span>
                        )}
                      </div>
                      <code className="mt-px block font-mono text-[11.5px] text-fg-tertiary dark:text-fg-tertiary-dark">{field.type}</code>
                      {field.description && (
                        <p className="mt-1.5 text-sm text-fg-secondary dark:text-fg-secondary-dark">{field.description}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        </SidePanel>
      )}
    </div>
  );
};
