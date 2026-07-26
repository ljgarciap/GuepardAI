import { CanActivateFn, Router } from '@angular/router';
import { inject } from '@angular/core';
import { catchError, map, of } from 'rxjs';
import { TosService } from '../services/tos.service';

/**
 * Corre después de authGuard en cada ruta protegida. Un usuario autenticado
 * pero sin el ToS vigente aceptado (default negativo, o revocado vía
 * "Reject") solo puede ver /tos — todo lo demás redirige ahí.
 */
export const tosGuard: CanActivateFn = (_route, state) => {
  const tosService = inject(TosService);
  const router = inject(Router);

  return tosService.fetchStatus().pipe(
    map((status) => status.accepted ? true : router.createUrlTree(['/tos'], { queryParams: { returnUrl: state.url } })),
    catchError(() => of(router.createUrlTree(['/tos'])))
  );
};
