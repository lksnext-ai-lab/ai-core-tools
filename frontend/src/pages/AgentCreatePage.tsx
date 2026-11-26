import { useNavigate, useParams } from 'react-router-dom';
import AgentQuickCreateForm from '../components/forms/AgentQuickCreateForm';
import type { Agent } from '../services/api';

/**
 * Quick creation for a new agent: only the name, type and first prompt. After saving,
 * the user chooses between the full form and the visual editor.
 */
function AgentCreatePage() {
  const { appId } = useParams();
  const navigate = useNavigate();

  const handleCreated = (agent: Agent, next: 'form' | 'visual') => {
    navigate(`/apps/${appId}/agents/${agent.agent_id}?view=${next}`);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 p-6 dark:from-gray-900 dark:to-gray-800">
      <div className="max-w-2xl mx-auto">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
            New agent
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mt-2">
            Name the agent and give it a first prompt. You can change everything afterwards.
          </p>
        </div>

        <section className="rounded-2xl border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-700 dark:bg-gray-800">
          <AgentQuickCreateForm
            appId={Number.parseInt(appId ?? '0')}
            onCreated={handleCreated}
            onCancel={() => navigate(`/apps/${appId}/agents`)}
            mode="page"
          />
        </section>
      </div>
    </div>
  );
}

export default AgentCreatePage;
