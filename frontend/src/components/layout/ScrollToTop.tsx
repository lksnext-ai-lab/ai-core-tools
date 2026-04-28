import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Resets the <main> scroll container to the top whenever the route changes.
 *
 * Lives inside <Router> so it can read `useLocation()`. Renders nothing.
 *
 * Why a dedicated component (vs. handling it in <Layout>): Layout is rendered
 * inside each route element, so it remounts on every navigation and there is no
 * reliable place to compare the previous and current pathnames. ScrollToTop is
 * mounted once at the Router level and just listens for path changes.
 */
function ScrollToTop() {
  const { pathname } = useLocation();

  useEffect(() => {
    const main = document.querySelector('main');
    if (main) {
      main.scrollTop = 0;
    }
    // Safety net: also reset the document scroll in case the layout overflowed
    // viewport (e.g. before the min-h-0 fixes propagate, or on legacy embedders).
    if (typeof window !== 'undefined') {
      window.scrollTo({ top: 0, left: 0 });
    }
  }, [pathname]);

  return null;
}

export default ScrollToTop;
