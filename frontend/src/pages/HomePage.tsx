import { Link } from 'react-router-dom';
import { ArrowRight, BarChart2, Info, AppWindow, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useUser } from '../contexts/UserContext';
import Title from '../components/ui/Title';
import CardApp from '../components/ui/CardApp';

function HomePage() {
  const { user } = useUser();
  const { t } = useTranslation('common');

  return (
    <div className="max-w-6xl mx-auto p-6">
      <Title
        variant="titPrincipal"
        titulo={t('homePage.title')}
        subtitulo={user?.name
          ? t('homePage.subtitleWithName', { name: user.name })
          : t('homePage.subtitle')}
        titleMarginBottom={16}
        subtitleMarginBottom={32}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        {/* Quick Actions */}
        <CardApp className="p-6" icon={AppWindow} titulo={t('breadcrumbs.navigation.myApps')}>
          <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm mb-4">
            {t('homePage.appsDescription')}
          </p>
          <Link 
            to="/apps"
            className="text-sm text-bronze  dark:text-bronze-dark inline-block"
          >
            {t('homePage.goToApps')} <ArrowRight className="w-4 h-4 inline-block ml-1" aria-hidden="true" />

          </Link>
        </CardApp>

        {/* Administration */}
        {user?.is_admin && (
          <CardApp className="p-6" icon={Users} titulo={t('breadcrumbs.navigation.users')}>
            <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm mb-4">
              {t('homePage.usersDescription')}
            </p>
            <Link 
              to="/admin/users"
              className="text-sm text-bronze  dark:text-bronze-dark inline-block"
            >
              {t('homePage.manageUsers')} <ArrowRight className="w-4 h-4 inline-block ml-1" aria-hidden="true" />
            </Link>
          </CardApp>
        )}

        {/* Statistics */}
        {user?.is_admin && (
          <CardApp className="p-6" icon={BarChart2} titulo={t('breadcrumbs.navigation.statistics')}>
            <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm mb-4">
              {t('homePage.statisticsDescription')}
            </p>
            <Link 
              to="/admin/stats"
              className="text-sm text-bronze  dark:text-bronze-dark inline-block"
            >
              {t('homePage.viewStats')} <ArrowRight className="w-4 h-4 inline-block ml-1" aria-hidden="true" />
            </Link>
          </CardApp>
        )}

        {/* About */}
        <CardApp className="p-6" icon={Info} titulo={t('breadcrumbs.navigation.about')}>
          <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm mb-4">
            {t('homePage.aboutDescription')}
          </p>
          <Link 
            to="/about"
            className="text-sm text-bronze  dark:text-bronze-dark inline-block"
          >
            {t('homePage.learnMore')} <ArrowRight className="w-4 h-4 inline-block ml-1" aria-hidden="true" />
          </Link>
        </CardApp>
      </div>

      {/* Getting Started Section */}
      <CardApp variant="canvas" className="p-6" titulo={t('homePage.gettingStartedTitle')}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="flex items-start space-x-3">
            <div className="w-6 h-6 bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark text-bronze dark:text-bronze-dark rounded-full flex items-center justify-center text-sm font-medium">1</div>
            <div>
              <h3 className="text-sm text-fg dark:text-fg-dark">{t('aboutPage.gettingStarted.createApp')}</h3>
              <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('homePage.createAppDescription')}</p>
            </div>
          </div>
          <div className="flex items-start space-x-3">
            <div className="w-6 h-6 bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark text-bronze dark:text-bronze-dark rounded-full flex items-center justify-center text-sm font-medium">2</div>
            <div>
              <h3 className="text-sm text-fg dark:text-fg-dark">{t('homePage.addAiAgents')}</h3>
              <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('homePage.addAiAgentsDescription')}</p>
            </div>
          </div>
          <div className="flex items-start space-x-3">
            <div className="w-6 h-6 bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark text-bronze dark:text-bronze-dark rounded-full flex items-center justify-center text-sm font-medium">3</div>
            <div>
              <h3 className="text-sm text-fg dark:text-fg-dark">{t('homePage.connectDataSources')}</h3>
              <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('homePage.connectDataSourcesDescription')}</p>
            </div>
          </div>
          <div className="flex items-start space-x-3">
            <div className="w-6 h-6 bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark text-bronze dark:text-bronze-dark rounded-full flex items-center justify-center text-sm font-medium">4</div>
            <div>
              <h3 className="text-sm text-fg dark:text-fg-dark">{t('homePage.deployAndMonitor')}</h3>
              <p className="text-sm text-fg-secondary dark:text-fg-secondary-dark">{t('homePage.deployAndMonitorDescription')}</p>
            </div>
          </div>
        </div>
      </CardApp>
    </div>
  );
}

export default HomePage;
