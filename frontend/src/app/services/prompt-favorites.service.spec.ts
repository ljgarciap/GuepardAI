/**
 * prompt-favorites.service.spec.ts — verifica método/URL/payload de cada
 * llamada HTTP del PromptFavoritesService (biblioteca-prompts-favoritos).
 */
import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { PromptFavoritesService } from './prompt-favorites.service';
import { environment } from '../../environments/environment';

describe('PromptFavoritesService', () => {
  let service: PromptFavoritesService;
  let httpMock: HttpTestingController;
  const API = environment.apiUrl;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [PromptFavoritesService],
    });
    service = TestBed.inject(PromptFavoritesService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('listFavorites() GETs /prompts/favorites', () => {
    service.listFavorites().subscribe();
    const req = httpMock.expectOne(`${API}/prompts/favorites`);
    expect(req.request.method).toBe('GET');
    req.flush([]);
  });

  it('createFavorite() POSTs the payload as-is', () => {
    const payload = { title: 'My favorite', prompt_text: 'Do a thing', prompt_metadata: { tone: 'urgent' } };
    service.createFavorite(payload).subscribe();
    const req = httpMock.expectOne(`${API}/prompts/favorites`);
    expect(req.request.method).toBe('POST');
    expect(req.request.body).toEqual(payload);
    req.flush({ id: 1, ...payload, source_job_id: null, owner_email: 'me@example.com', created_at: '', updated_at: '' });
  });

  it('updateFavorite() PUTs to /prompts/favorites/{id}', () => {
    service.updateFavorite(9, { title: 'Renamed' }).subscribe();
    const req = httpMock.expectOne(`${API}/prompts/favorites/9`);
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({ title: 'Renamed' });
    req.flush({
      id: 9, title: 'Renamed', prompt_text: 'x', prompt_metadata: null,
      source_job_id: null, owner_email: 'me@example.com', created_at: '', updated_at: '',
    });
  });

  it('deleteFavorite() DELETEs /prompts/favorites/{id}', () => {
    service.deleteFavorite(9).subscribe();
    const req = httpMock.expectOne(`${API}/prompts/favorites/9`);
    expect(req.request.method).toBe('DELETE');
    req.flush({ deleted: true, id: 9 });
  });
});
