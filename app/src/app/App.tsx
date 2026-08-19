import { Home } from '../ui/Home'
import { Review } from '../ui/Review'
import { useRoute } from './useRoute'

export function App() {
  const route = useRoute()

  switch (route.name) {
    case 'home':
      return <Home />
    case 'review':
      return <Review />
  }
}
