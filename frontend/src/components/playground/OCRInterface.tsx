import React, { useState, useRef } from 'react';
import { apiService } from '../../services/api';
import MessageContent from './MessageContent';

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

export const OCRInterface: React.FC<OCRInterfaceProps> = ({
  appId,
  agentId,
  agentName,
  outputParser,
  onError
}) => {
  const [results, setResults] = useState<OCRResult[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      
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
        extractedText: response.extracted_text || 'No text extracted',
        metadata: response.metadata,
        result: response.result // For structured results
      };

      setResults(prev => [result, ...prev]);
      setSelectedFile(null);
      setPdfPreviewUrl(null);
      
      // Reset file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    } catch (error) {
      console.error('OCR processing error:', error);
      onError?.(error instanceof Error ? error.message : 'Failed to process document');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleClearResults = () => {
    setResults([]);
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
    a.download = `${result.originalFile.name.replace(/\.[^/.]+$/, '')}_result.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Agent Information Card */}
      <div className="bg-white rounded-lg shadow-sm border">
        <div className="p-4 border-b bg-gray-50 rounded-t-lg">
          <h3 className="text-lg font-semibold text-gray-900">
            <span className="mr-2">🤖</span>
            Playground OCR: {agentName}
          </h3>
        </div>
        <div className="p-4">
          <p className="text-sm text-gray-600 mb-4">
            Upload a PDF document to extract text and structured data using OCR processing
          </p>
          
          {/* Output Parser Information */}
          {outputParser && (
            <div className="mt-4 p-4 bg-blue-50 rounded-lg">
              <h4 className="text-sm font-medium text-blue-900 mb-2">
                <span className="mr-2">📋</span>
                Formato de salida: {outputParser.name}
              </h4>
              {outputParser.description && (
                <p className="text-sm text-blue-700 mb-3">{outputParser.description}</p>
              )}
              {outputParser.fields && outputParser.fields.length > 0 && (
                <div>
                  <h5 className="text-xs font-medium text-blue-800 mb-2">Campos de salida:</h5>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                    {outputParser.fields.map((field, index) => (
                      <div key={index} className="bg-white p-2 rounded border text-xs">
                        <div className="font-medium text-blue-900">{field.name}</div>
                        <div className="text-blue-600">
                          <code className="text-xs">{field.type}</code>
                        </div>
                        {field.description && (
                          <div className="text-blue-500 mt-1">{field.description}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Processing Card */}
      <div className="bg-white rounded-lg shadow-sm border">
        <div className="p-4 border-b bg-gray-50 rounded-t-lg">
          <h4 className="text-md font-medium text-gray-900">
            <span className="mr-2">📄</span>
            Procesar PDF
          </h4>
        </div>
        <div className="p-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left Column: File Upload and Preview */}
            <div className="space-y-4">
              {/* File Upload Area */}
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-gray-400 transition-colors">
                <div className="mb-4">
                  <svg className="mx-auto h-12 w-12 text-gray-400" stroke="currentColor" fill="none" viewBox="0 0 48 48">
                    <path d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </div>
                <p className="text-sm text-gray-600 mb-2">Arrastra un archivo PDF aquí o</p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
                >
                  Seleccionar archivo
                </button>
              </div>

              {/* PDF Preview */}
              {pdfPreviewUrl && (
                <div className="border rounded-lg overflow-hidden">
                  <div className="p-3 bg-gray-50 border-b">
                    <h5 className="text-sm font-medium text-gray-900">
                      <span className="mr-2">👁️</span>
                      Vista previa del documento
                    </h5>
                  </div>
                  <iframe
                    src={pdfPreviewUrl}
                    className="w-full h-96"
                    title="PDF Preview"
                  />
                </div>
              )}

              {/* Process Button */}
              {selectedFile && (
                <button
                  onClick={handleProcessOCR}
                  disabled={isProcessing}
                  className="w-full bg-green-600 text-white py-3 px-4 rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isProcessing ? (
                    <div className="flex items-center justify-center">
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                      Procesando...
                    </div>
                  ) : (
                    'Procesar PDF'
                  )}
                </button>
              )}
            </div>

            {/* Right Column: Results */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h5 className="text-md font-medium text-gray-900">
                  <span className="mr-2">📊</span>
                  Resultados del procesamiento
                </h5>
                {results.length > 0 && (
                  <button
                    onClick={handleClearResults}
                    className="text-sm text-red-600 hover:text-red-700 hover:bg-red-50 px-2 py-1 rounded transition-colors"
                  >
                    Limpiar todo
                  </button>
                )}
              </div>

              {results.length === 0 && !isProcessing && (
                <div className="text-center text-gray-500 py-8">
                  <p>No hay documentos procesados aún</p>
                  <p className="text-sm mt-2">Sube un documento para comenzar</p>
                </div>
              )}

              {results.map((result) => (
                <div key={result.id} className="border rounded-lg p-4 bg-gray-50">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <h6 className="font-medium text-gray-900">{result.originalFile.name}</h6>
                      <p className="text-sm text-gray-500">
                        {result.timestamp.toLocaleString()}
                      </p>
                    </div>
                    <button
                      onClick={() => downloadResult(result)}
                      className="text-blue-600 hover:text-blue-700 text-sm"
                    >
                      📥 Descargar
                    </button>
                  </div>

                  {/* Structured Results (from output parser) */}
                  {result.result?.content && (
                    <div className="mb-3">
                      <h6 className="font-medium text-gray-700 mb-2">Datos estructurados:</h6>
                      <div className="bg-white p-3 rounded border">
                        <MessageContent content={
                          typeof result.result.content === 'object' 
                            ? result.result.content 
                            : result.result.content
                        } />
                      </div>
                    </div>
                  )}

                  {/* Extracted Text */}
                  {result.extractedText && (
                    <div className="mb-3">
                      <h6 className="font-medium text-gray-700 mb-2">Texto extraído:</h6>
                      <div className="bg-white p-3 rounded border">
                        <div className="max-h-32 overflow-y-auto">
                          <pre className="text-sm text-gray-800 whitespace-pre-wrap">
                            {result.extractedText}
                          </pre>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Metadata */}
                  {result.metadata && (
                    <div>
                      <h6 className="font-medium text-gray-700 mb-2">Metadatos:</h6>
                      <div className="bg-white p-3 rounded border">
                        <pre className="text-sm text-gray-600">
                          {JSON.stringify(result.metadata, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}; 