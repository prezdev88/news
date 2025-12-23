import { enableProdMode } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { provideAnimations } from '@angular/platform-browser/animations';
import { provideHttpClient, withFetch } from '@angular/common/http';
import { provideRouter, Routes } from '@angular/router';
import { AppComponent } from './app/app.component';
import { environment } from './environments/environment';
import { HomeComponent } from './app/home.component';
import { FiltersComponent } from './app/filters.component';

const routes: Routes = [
  { path: '', component: HomeComponent },
  { path: 'filtros', component: FiltersComponent },
  { path: '**', redirectTo: '' }
];

if (environment.production) {
  enableProdMode();
}

bootstrapApplication(AppComponent, {
  providers: [
    provideHttpClient(withFetch()),
    provideAnimations(),
    provideRouter(routes)
  ]
}).catch(err => console.error(err));
