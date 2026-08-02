import { Navigate, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Profile from './pages/Profile'
import ProfileIntake from './pages/ProfileIntake'
import { AppLayout } from './components/layout/AppLayout'
import { ToastProvider } from './components/ui/Toast'

export default function App() {
  return (
    <ToastProvider>
      <AppLayout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/profile/setup" element={<ProfileIntake />} />
          <Route path="/profile/intake" element={<Navigate to="/profile/setup" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppLayout>
    </ToastProvider>
  );
}
