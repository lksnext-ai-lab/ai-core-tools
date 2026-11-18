import { useState } from 'react';
import { Loader2, Plug } from 'lucide-react';
import type { ActionItem } from '../ui/ActionDropdown';
import ServiceConnectionTestModal from './ServiceConnectionTestModal';
import type { TestConnectionResult } from './serviceApi';

type TestConnection = () => Promise<TestConnectionResult>;

interface TestService {
  readonly id: number;
  readonly name: string;
}

export type ServiceKindLabel = 'AI' | 'embedding' | 'sandbox';

export function useServiceConnectionTest(serviceKind: ServiceKindLabel) {
  const [testService, setTestService] = useState<TestService | null>(null);
  const [testingServiceId, setTestingServiceId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null);

  const runTest = async (
    service: TestService,
    testConnection: TestConnection,
  ): Promise<void> => {
    if (testingServiceId !== null) return;

    setTestService(service);
    setTestingServiceId(service.id);
    setTestResult(null);
    try {
      setTestResult(await testConnection());
    } catch (err) {
      setTestResult({
        status: 'error',
        message: err instanceof Error ? err.message : 'Failed to test connection',
      });
    } finally {
      setTestingServiceId(null);
    }
  };

  const testAction = (
    serviceId: number,
    serviceName: string,
    testConnection: TestConnection,
  ): ActionItem => ({
    label: testingServiceId === serviceId ? 'Testing...' : 'Test Connection',
    onClick: () => {
      void runTest({ id: serviceId, name: serviceName }, testConnection);
    },
    icon: testingServiceId === serviceId
      ? <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
      : <Plug className="w-4 h-4" aria-hidden="true" />,
    variant: 'success',
    disabled: testingServiceId !== null,
  });

  const modal = testService && (
    <ServiceConnectionTestModal
      isOpen
      isTesting={testingServiceId !== null}
      serviceName={testService.name}
      serviceKind={serviceKind}
      result={testResult}
      onClose={() => {
        if (testingServiceId === null) setTestService(null);
      }}
    />
  );

  return { testAction, modal };
}
