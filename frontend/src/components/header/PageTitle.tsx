import React from 'react';
import type { NavigationConfig } from '../../core/types';
import { Breadcrumbs } from './Breadcrumbs';

interface PageTitleProps {
  navigationConfig?: NavigationConfig;
}

export const PageTitle: React.FC<PageTitleProps> = ({ navigationConfig }) => (
  <Breadcrumbs navigationConfig={navigationConfig} />
);