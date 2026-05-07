import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/resumes')({
  component: ResumesPage,
})

function ResumesPage() {
  return <div>Resume list — placeholder</div>
}
