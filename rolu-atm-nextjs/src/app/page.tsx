import { WorldIdSignIn } from '@/components/WorldIdSignIn';

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="max-w-md w-full space-y-8 p-8 bg-white rounded-xl shadow-lg">
        <div className="text-center">
          <div className="mx-auto h-16 w-16 bg-indigo-600 rounded-full flex items-center justify-center mb-4">
            <span className="text-2xl">🏧</span>
          </div>
          <h1 className="text-3xl font-bold text-gray-900">RoluATM</h1>
          <p className="mt-2 text-gray-600">Secure cash withdrawal with World ID</p>
        </div>
        
        <WorldIdSignIn />
        
        <div className="text-center">
          <div className="flex items-center justify-center space-x-4 text-xs text-gray-400">
            <span>🔒 Secure</span>
            <span>•</span>
            <span>🌍 Private</span>
            <span>•</span>
            <span>⚡ Fast</span>
          </div>
        </div>
      </div>
    </div>
  );
}
