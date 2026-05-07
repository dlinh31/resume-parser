import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/resumes/$fileId')({
  component: ResumeDetailPage,
})

function ResumeDetailPage() {
  const { fileId } = Route.useParams()
  return <div>Resume detail — {fileId}</div>
}
