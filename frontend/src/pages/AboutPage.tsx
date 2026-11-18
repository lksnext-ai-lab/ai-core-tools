import React from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, Search, Database, Wrench, Zap, Sprout, Building2, Brain } from 'lucide-react';
import { ButtonLink } from '../components/ui/ButtonLink';
import CardApp from '../components/ui/CardApp';

const AboutPage: React.FC = () => {
  const { t } = useTranslation('common');

  return (
    <div className="max-w-6xl mx-auto p-8">
      {/* Hero Section */}
      <div className="text-center mb-12">
        <div className="flex justify-center mb-6">
          <div className="w-24 h-24 bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark rounded-lg flex items-center justify-center">
            <Bot className="w-12 h-12 text-bronze dark:text-bronze-dark" />
          </div>
        </div>
        <h1 className="text-5xl text-ink dark:text-ink-dark font-normal leading-[1.1]  tracking-[-0.8px] mb-4">
          Mattin AI
        </h1>
        <p className="text-xl text-fg-secondary dark:text-fg-secondary-dark">
          {t('aboutPage.hero.tagline')}
        </p>
        <p className="text-lg text-fg-tertiary dark:text-fg-tertiary-dark max-w-3xl mx-auto">
          {t('aboutPage.hero.description')}
        </p>
      </div>

      {/* Overview Section */}
      <CardApp className="p-8 mb-8">
        <h2 className="text-3xl font-bold text-fg dark:text-fg-dark mb-6">{t('aboutPage.overview.title')}</h2>
        <div className="grid md:grid-cols-2 gap-8">
          <div>
            <p className="text-lg text-fg-secondary dark:text-fg-secondary-dark mb-4">
              {t('aboutPage.overview.description1')}
            </p>
            <p className="text-lg text-fg-secondary dark:text-fg-secondary-dark mb-4">
              {t('aboutPage.overview.description2')}
            </p>
          </div>
          <CardApp variant="canvas" className="p-6" titulo={t('aboutPage.overview.highlightsTitle')}>
             <ul className="space-y-3">
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.overview.highlightOpenSource')}</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.overview.highlightExtensible')}</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.overview.highlightProviders')}</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.overview.highlightEnterprise')}</span>
              </li>
            </ul>
          </CardApp>
        </div>
      </CardApp>

      {/* Features Section */}
      <CardApp className="p-8 mb-8">
        <h2 className="text-3xl font-bold text-fg dark:text-fg-dark mb-8 text-center">{t('aboutPage.features.title')}</h2>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          <CardApp variant='canvas' className="p-6 ">
            <div className="w-12 h-12 border border-accent rounded-md flex items-center justify-center mb-4">
              <Brain className="w-8 h-8 text-fg dark:text-fg-dark" />
            </div>
            <h3 className="text-xl font-semibold text-fg dark:text-fg-dark mb-3">{t('aboutPage.features.llmTitle')}</h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark">
              {t('aboutPage.features.llmDescription')}
            </p>
          </CardApp>

          <CardApp variant="canvas" className="p-6">
            <div className="w-12 h-12 border border-accent rounded-md flex items-center justify-center mb-4">
              <Search className="w-8 h-8 text-fg dark:text-fg-dark" />
            </div>
            <h3 className="text-xl font-semibold text-fg dark:text-fg-dark mb-3">{t('aboutPage.features.ragTitle')}</h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark">
              {t('aboutPage.features.ragDescription')}
            </p>
          </CardApp>

          <CardApp variant="canvas" className="p-6">
            <div className="w-12 h-12 border border-accent rounded-md flex items-center justify-center mb-4">
              <Database className="w-8 h-8  text-fg dark:text-fg-dark" />
            </div>
            <h3 className="text-xl font-semibold  text-fg dark:text-fg-dark mb-3">{t('aboutPage.features.vectorTitle')}</h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark">
              {t('aboutPage.features.vectorDescription')}
            </p>
          </CardApp>

          <CardApp variant="canvas" className="p-6">
            <div className="w-12 h-12 border border-accent rounded-md flex items-center justify-center mb-4">
              <Bot className="w-8 h-8  text-fg dark:text-fg-dark" />
            </div>
            <h3 className="text-xl font-semibold  text-fg dark:text-fg-dark mb-3">{t('aboutPage.features.agentsTitle')}</h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark">
              {t('aboutPage.features.agentsDescription')}
            </p>
          </CardApp>

          <CardApp variant="canvas" className="p-6">
            <div className="w-12 h-12 border border-accent rounded-md flex items-center justify-center mb-4">
              <Wrench className="w-8 h-8  text-fg dark:text-fg-dark" />
            </div>
            <h3 className="text-xl font-semibold  text-fg dark:text-fg-dark mb-3">{t('aboutPage.features.modularTitle')}</h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark">
              {t('aboutPage.features.modularDescription')}
            </p>
          </CardApp>

          <CardApp variant="canvas" className="p-6">
            <div className="w-12 h-12 border border-accent rounded-md flex items-center justify-center mb-4">
              <Zap className="w-8 h-8  text-fg dark:text-fg-dark" />
            </div>
            <h3 className="text-xl font-semibold  text-fg dark:text-fg-dark mb-3">{t('aboutPage.features.performanceTitle')}</h3>
            <p className="text-fg-secondary dark:text-fg-secondary-dark">
              {t('aboutPage.features.performanceDescription')}
            </p>
          </CardApp>
        </div>
      </CardApp>

      {/* Architecture Section */}
      <CardApp className=" p-8 mb-8">
        <h2 className="text-3xl font-bold text-fg dark:text-fg-dark mb-8 text-center">{t('aboutPage.architecture.title')}</h2>
        <div className="grid lg:grid-cols-2 gap-8">
          <div>
            <h3 className="text-xl font-semibold text-fg dark:text-fg-dark mb-4">{t('aboutPage.architecture.technologyStack')}</h3>
            <div className="space-y-4">
              <CardApp variant="canvas" className="!flex-row items-center">
                <div className="w-10 h-10  p-4 rounded-md border-[1.5px] border-accent bg-surface text-[15px] font-medium text-ink dark:border-accent-dark dark:bg-surface-dark dark:text-ink-dark flex items-center justify-center mr-4">
                  <span className="text-fg dark:text-fg-dark font-bold">P</span>
                </div>
                <div>
                  <h4 className="font-semibold text-fg dark:text-fg-dark">{t('aboutPage.architecture.backend')}</h4>
                  <p className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.architecture.backendDescription')}</p>
                </div>
              </CardApp>
              <CardApp variant="canvas" className="!flex-row items-center">
                <div className="w-10 h-10  p-4 rounded-md border-[1.5px] border-accent bg-surface text-[15px] font-medium text-ink dark:border-accent-dark dark:bg-surface-dark dark:text-ink-dark flex items-center justify-center mr-4">
                  <span className="text-fg dark:text-fg-dark font-bold">R</span>
                </div>
                <div>
                  <h4 className="font-semibold text-fg dark:text-fg-dark">{t('aboutPage.architecture.frontend')}</h4>
                  <p className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.architecture.frontendDescription')}</p>
                </div>
              </CardApp>
              <CardApp variant="canvas" className="!flex-row items-center">
                <div className="w-10 h-10  p-4 rounded-md border-[1.5px] border-accent bg-surface text-[15px] font-medium text-ink dark:border-accent-dark dark:bg-surface-dark dark:text-ink-dark flex items-center justify-center mr-4">
                  <span className="text-fg dark:text-fg-dark font-bold">DB</span>
                </div>
                <div>
                  <h4 className="font-semibold text-fg dark:text-fg-dark">{t('aboutPage.architecture.database')}</h4>
                  <p className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.architecture.databaseDescription')}</p>
                </div>
              </CardApp>
              <CardApp variant="canvas" className="!flex-row items-center">
                <div className="w-10 h-10  p-4 rounded-md border-[1.5px] border-accent bg-surface text-[15px] font-medium text-ink dark:border-accent-dark dark:bg-surface-dark dark:text-ink-dark flex items-center justify-center mr-4">
                  <span className="text-fg dark:text-fg-dark font-bold">AI</span>
                </div>
                <div>
                  <h4 className="font-semibold text-fg dark:text-fg-dark">{t('aboutPage.architecture.aiServices')}</h4>
                  <p className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.architecture.aiServicesDescription')}</p>
                </div>
              </CardApp>
            </div>
          </div>
          <div>
            <h3 className="text-xl font-semibold text-fg dark:text-fg-dark mb-4">{t('aboutPage.architecture.keyComponents')}</h3>
            <div className="space-y-3">
              <div className="flex items-start">
                <div className="w-3 h-3 bg-bronze dark:bg-bronze-dark rounded-full mt-2 mr-3"></div>
                <div>
                  <h4 className="font-semibold text-fg dark:text-fg-dark">{t('aboutPage.architecture.restApi')}</h4>
                  <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm">{t('aboutPage.architecture.restApiDescription')}</p>
                </div>
              </div>
              <div className="flex items-start">
                <div className="w-3 h-3 bg-bronze dark:bg-bronze-dark rounded-full mt-2 mr-3"></div>
                <div>
                  <h4 className="font-semibold text-fg dark:text-fg-dark">{t('aboutPage.architecture.authentication')}</h4>
                  <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm">{t('aboutPage.architecture.authenticationDescription')}</p>
                </div>
              </div>
              <div className="flex items-start">
                <div className="w-3 h-3 bg-bronze dark:bg-bronze-dark rounded-full mt-2 mr-3"></div>
                <div>
                  <h4 className="font-semibold text-fg dark:text-fg-dark">{t('aboutPage.architecture.vectorStorage')}</h4>
                  <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm">{t('aboutPage.architecture.vectorStorageDescription')}</p>
                </div>
              </div>
              <div className="flex items-start">
                <div className="w-3 h-3 bg-bronze dark:bg-bronze-dark rounded-full mt-2 mr-3"></div>
                <div>
                  <h4 className="font-semibold text-fg dark:text-fg-dark">{t('aboutPage.architecture.agentFramework')}</h4>
                  <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm">{t('aboutPage.architecture.agentFrameworkDescription')}</p>
                </div>
              </div>
              <div className="flex items-start">
                <div className="w-3 h-3 bg-bronze dark:bg-bronze-dark rounded-full mt-2 mr-3"></div>
                <div>
                  <h4 className="font-semibold text-fg dark:text-fg-dark">{t('aboutPage.architecture.webInterface')}</h4>
                  <p className="text-fg-secondary dark:text-fg-secondary-dark text-sm">{t('aboutPage.architecture.webInterfaceDescription')}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </CardApp>

      {/* Licensing Section */}
      <CardApp className="p-8 mb-8">
        <h2 className="text-3xl font-bold text-fg dark:text-fg-dark mb-8 text-center">{t('aboutPage.licensing.title')}</h2>
        <div className="!grid grid-cols-1 gap-6 p-6 lg:grid-cols-2">
          <CardApp className="p-6">
            <div className="flex items-center mb-4">
              <div className="w-12 h-12 bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark rounded-lg flex items-center justify-center mr-4">
                <Sprout className="w-8 h-8 text-bronze dark:text-bronze-dark" />
              </div>
              <h3 className="text-2xl font-bold text-fg dark:text-fg-dark">{t('aboutPage.licensing.openSource')}</h3>
            </div>
            <p className="text-fg-secondary dark:text-fg-secondary-dark mb-4">
              <strong>{t('aboutPage.licensing.agpl')}</strong>
            </p>
            <ul className="space-y-2 text-fg-secondary dark:text-fg-secondary-dark">
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.licensing.freeUse')}</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.licensing.community')}</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.licensing.networkDisclosure')}</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.licensing.copyleft')}</span>
              </li>
            </ul>
          </CardApp>

          <CardApp className="p-6">
            <div className="flex items-center mb-4">
              <div className="w-12 h-12 bg-bronze-bg-soft dark:bg-bronze-bg-soft-dark rounded-lg flex items-center justify-center mr-4">
                <Building2 className="w-8 h-8 text-bronze dark:text-bronze-dark" />
              </div>
              <h3 className="text-2xl font-bold text-fg dark:text-fg-dark">{t('aboutPage.licensing.commercial')}</h3>
            </div>
            <p className="text-fg-secondary dark:text-fg-secondary-dark mb-4">
              <strong>{t('aboutPage.licensing.commercialLicense')}</strong>
            </p>
            <ul className="space-y-2 text-fg-secondary dark:text-fg-secondary-dark">
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.licensing.fullFunctionality')}</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.licensing.commercialUse')}</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.licensing.clientModifications')}</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.licensing.enterpriseSupport')}</span>
              </li>
              <li className="flex items-center">
                <span className="w-2 h-2 bg-bronze dark:bg-bronze-dark rounded-full mr-3" />
                <span className="text-fg-secondary dark:text-fg-secondary-dark">{t('aboutPage.licensing.noDisclosure')}</span>
              </li>
            </ul>
          </CardApp>
        </div>
        <div className="mt-6 text-center">
          <p className="text-fg-secondary dark:text-fg-secondary-dark mb-4">
            <strong>{t('aboutPage.licensing.contact')}</strong>
          </p>
          <div className="flex justify-center space-x-4">
            <ButtonLink
              to="https://github.com/lksnext-ai-lab/ai-core-tools"
              label={t('aboutPage.licensing.viewOnGitHub')}
              target="_blank"
              rel="noopener noreferrer"
              variant="primary"
              size="medium"
            />
            <ButtonLink
              to="/apps"
              label={t('aboutPage.licensing.getStarted')}
              variant="secondary"
              size="medium"
            />
          </div>
        </div>
      </CardApp>

      {/* Getting Started Section */}
      <CardApp className="p-8 mb-8">
        <h2 className="text-3xl font-bold text-fg dark:text-fg-dark mb-8 text-center">{t('aboutPage.gettingStarted.title')}</h2>
        <div className="text-center">
          <p className="text-lg text-fg-secondary dark:text-fg-secondary-dark mb-6">
            {t('aboutPage.gettingStarted.description')}
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <ButtonLink
              to="/apps"
              label={t('aboutPage.gettingStarted.createApp')}
              variant="primary"
              size="medium"
            />
            <ButtonLink
              to="/apps"
              label={t('aboutPage.gettingStarted.configureServices')}
              variant="secondary"
              size="medium"
            />
          </div>
        </div>
      </CardApp>

      {/* Footer Info */}
      <div className="text-center text-fg-tertiary dark:text-fg-tertiary-dark text-sm">
        <p>{t('aboutPage.footer.copyright')}</p>
        <p className="mt-2">
          {t('aboutPage.footer.builtWith')}
        </p>
      </div>
    </div>
  );
};

export default AboutPage;
