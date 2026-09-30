import { SessionGate } from './SessionGate';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

function ProtectedRoute({ children }: Readonly<ProtectedRouteProps>) {
  return <SessionGate>{() => children}</SessionGate>;
}

export default ProtectedRoute;
