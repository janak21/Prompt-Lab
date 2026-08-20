import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/AppShell'
import { Toaster } from '@/components/ui'
import { PromptsPage } from '@/pages/Prompts'
import { PromptDetailPage } from '@/pages/PromptDetail'
import { DatasetsPage } from '@/pages/Datasets'
import { DatasetDetailPage } from '@/pages/DatasetDetail'
import { RunsPage } from '@/pages/Runs'
import { RunDetailPage } from '@/pages/RunDetail'
import { ComparePage } from '@/pages/Compare'
import { SettingsPage } from '@/pages/Settings'
import { KitchenSinkPage } from '@/pages/KitchenSink'

function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<Navigate to="/prompts" replace />} />
        <Route path="/prompts" element={<PromptsPage />} />
        <Route path="/prompts/:id" element={<PromptDetailPage />} />
        <Route path="/datasets" element={<DatasetsPage />} />
        <Route path="/datasets/:id" element={<DatasetDetailPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:id" element={<RunDetailPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/settings" element={<SettingsPage />} />
        {import.meta.env.DEV && <Route path="/kitchen-sink" element={<KitchenSinkPage />} />}
        <Route path="*" element={<Navigate to="/prompts" replace />} />
      </Routes>
      <Toaster />
    </AppShell>
  )
}

export default App
