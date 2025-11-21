export const getProviderBadgeColor = (provider: string) => {
  const p = provider || '';
  const normalized = p.toLowerCase();
  const map: Record<string, string> = {
    'openai': 'bg-green-100 text-green-800',
    'azure': 'bg-blue-100 text-blue-800',
    'anthropic': 'bg-purple-100 text-purple-800',
    'ollama': 'bg-orange-100 text-orange-800',
    'mistralai': 'bg-purple-100 text-purple-800',
    'custom': 'bg-gray-100 text-gray-800'
  };
  return map[normalized] || 'bg-gray-100 text-gray-800';
};
