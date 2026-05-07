import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/')({
  component: UploadPage,
})

function UploadPage() {
  return <div>Upload page — placeholder</div>
}
