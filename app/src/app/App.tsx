import { Home } from '../ui/Home'
import { Reader } from '../ui/Reader'
import { Review } from '../ui/Review'
import { useRoute } from './useRoute'

export function App() {
  const route = useRoute()

  switch (route.name) {
    case 'home':
      return <Home />
    case 'review':
      return <Review />
    case 'reader':
      return (
        <Reader
          // Remounting on a track change is what resets the reveal-all
          // toggle, which §10.2 scopes to one reading pass.
          key={route.trackId}
          trackId={route.trackId}
        />
      )
  }
}
