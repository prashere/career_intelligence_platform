import { Navigate, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Profile from './pages/Profile'
import ProfileIntake from './pages/ProfileIntake'
import Login from './pages/Login'
import Register from './pages/Register'
import AdminSchedulers from './pages/AdminSchedulers'
import AdminIngestion from './pages/AdminIngestion'
import AdminIngestionPlayground from './pages/AdminIngestionPlayground'
import AdminSources from './pages/AdminSources'
import { AppLayout } from './components/layout/AppLayout'
import { ToastProvider } from './components/ui/Toast'
import { AdminRoute, GuestRoute, ProtectedRoute } from './auth/ProtectedRoute'

export default function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route path="/login" element={<GuestRoute><Login /></GuestRoute>} />
        <Route path="/register" element={<GuestRoute><Register /></GuestRoute>} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <AppLayout>
                <Routes>
                  <Route path="/" element={<Dashboard />} />
                  <Route path="/profile" element={<Profile />} />
                  <Route path="/profile/setup" element={<ProfileIntake />} />
                  <Route path="/profile/intake" element={<Navigate to="/profile/setup" replace />} />
                  <Route path="/admin/schedulers" element={<AdminRoute><AdminSchedulers /></AdminRoute>} />
                  <Route path="/admin/ingestion" element={<AdminRoute><AdminIngestion /></AdminRoute>} />
                  <Route path="/admin/sources" element={<AdminRoute><AdminSources /></AdminRoute>} />
                  <Route path="/admin/ingestion/playground" element={<AdminRoute><AdminIngestionPlayground /></AdminRoute>} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </AppLayout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </ToastProvider>
  );
}
