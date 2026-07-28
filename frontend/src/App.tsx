import { Navigate, Route, Routes } from 'react-router-dom';
import { AppLayout } from './components/layout/AppLayout';
import { ToastProvider } from './components/ui/Toast';
import Feed from './pages/Feed';
import Detail from './pages/Detail';
import Dashboard from './pages/Dashboard';
import Profile from './pages/Profile';
import { IntakeWizard } from './pages/ProfileIntake';
import Planning from './pages/Planning';
import Learning from './pages/Learning';
import Discover from './pages/Discover';

export default function App() {
  return (
    <ToastProvider>
      <AppLayout>
        <Routes>
          <Route path="/" element={<Feed />} />
          <Route path="/opportunities/:id" element={<Detail />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/planning" element={<Planning />} />
          <Route path="/learning" element={<Learning />} />
          <Route path="/discover" element={<Discover />} />
          <Route path="/profile" element={<Navigate to="/profile/intake" replace />} />
          <Route path="/profile/intake" element={<IntakeWizard />} />
          <Route path="/profile/ranking" element={<Profile />} />
        </Routes>
      </AppLayout>
    </ToastProvider>
  );
}
