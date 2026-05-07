import { useSearchParams } from 'react-router-dom';
import { Lock, Mail, ExternalLink } from 'lucide-react';

function EnterpriseFeaturePage() {
  const [params] = useSearchParams();
  const featureName = params.get('feature') ?? 'this feature';

  return (
    <div className="max-w-2xl mx-auto py-16 px-4 text-center">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-amber-50 border border-amber-200 mb-6">
        <Lock className="w-8 h-8 text-amber-500" />
      </div>

      <h1 className="text-2xl font-bold text-gray-900 mb-3">
        Enterprise Edition
      </h1>

      <p className="text-gray-600 mb-2">
        <span className="font-medium capitalize">{featureName}</span> is part of the Mattin AI Enterprise Edition.
      </p>

      <p className="text-gray-500 text-sm mb-8">
        Enterprise modules extend the platform with advanced connectors, integrations, and capabilities
        designed for large organisations.
      </p>

      <div className="bg-gray-50 border border-gray-200 rounded-xl p-6 text-left mb-8">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-4">
          What you get with Enterprise Edition
        </h2>
        <ul className="space-y-2 text-sm text-gray-600">
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-green-500 font-bold">✓</span>
            <span><strong>SharePoint Sync</strong> — Index Microsoft SharePoint and OneDrive drives directly into your silos with incremental delta sync</span>
          </li>
          <li className="flex items-start gap-2">
            <span className="mt-0.5 text-gray-300 font-bold">+</span>
            <span className="text-gray-400">More Enterprise connectors and integrations coming soon</span>
          </li>
        </ul>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 justify-center">
        <a
          href="mailto:info@lksnext.com?subject=Mattin AI Enterprise Edition"
          className="inline-flex items-center justify-center gap-2 px-5 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Mail className="w-4 h-4" />
          Contact us to purchase
        </a>
        <a
          href="https://lksnext.com"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center gap-2 px-5 py-2.5 border border-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-50 transition-colors"
        >
          <ExternalLink className="w-4 h-4" />
          Learn more
        </a>
      </div>
    </div>
  );
}

export default EnterpriseFeaturePage;
