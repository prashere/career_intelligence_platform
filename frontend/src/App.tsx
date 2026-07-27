import { NavLink, Route, Routes } from 'react-router-dom'
import Feed from './pages/Feed'
import Detail from './pages/Detail'
import Dashboard from './pages/Dashboard'
import Profile from './pages/Profile'
import ProfileIntake from './pages/ProfileIntake'
import Planning from './pages/Planning'
import Learning from './pages/Learning'
import Discover from './pages/Discover'

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>Career Intelligence</h1>
        <nav>
          <NavLink to="/" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`} end>
            Opportunities
          </NavLink>
          <NavLink to="/dashboard" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Dashboard
          </NavLink>
          <NavLink to="/planning" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Weekly Plan
          </NavLink>
          <NavLink to="/learning" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Upskilling
          </NavLink>
          <NavLink to="/discover" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            People & Communities
          </NavLink>
          <NavLink to="/profile" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            Profile
          </NavLink>
        </nav>
      </aside>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Feed />} />
          <Route path="/opportunities/:id" element={<Detail />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/planning" element={<Planning />} />
          <Route path="/learning" element={<Learning />} />
          <Route path="/discover" element={<Discover />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/profile/intake" element={<ProfileIntake />} />
        </Routes>
      </main>
    </div>
  )
}
