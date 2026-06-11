/**
 * brand.service.spec.ts - Tests de Servicios Angular (API Communication)
 * =========================================================================
 * Objetivo: Probar todos los métodos del BrandService que se comunican con
 * el Backend API, sin hacer llamadas HTTP reales.
 *
 * Estrategia:
 *  - Se usa HttpClientTestingModule para interceptar las peticiones HTTP.
 *  - HttpTestingController verifica URL, método HTTP y payload enviados.
 *  - Cada test verifica que la respuesta del mock se propaga correctamente.
 *  - NO se prueban componentes visuales, solo la lógica de comunicación.
 *
 * Cobertura:
 *  - generatePresentation(): Flujo principal de generación.
 *  - getGenerationStatus(): Polling de estado del Job.
 *  - getBrands() / createBrand() / updateBrand(): CRUD de Brands.
 *  - uploadBrandAsset(): Upload de assets.
 *  - getAvailableStyles() / getAvailableKnowledge(): Catálogos.
 *  - getLibrary*(): Métodos de la biblioteca de assets.
 */
import { TestBed } from '@angular/core/testing';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { BrandService } from './brand.service';
import { environment } from '../../environments/environment';

describe('BrandService', () => {
  let service: BrandService;
  let httpMock: HttpTestingController;
  const API = environment.apiUrl;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [BrandService],
    });
    service = TestBed.inject(BrandService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    // Verifica que no haya peticiones HTTP pendientes sin interceptar.
    // Esto previene que un test olvide consumir una petición.
    httpMock.verify();
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Tests de Generación de Presentaciones (Flujo Principal)
  // ─────────────────────────────────────────────────────────────────────────

  describe('generatePresentation()', () => {
    it('should POST to /presentations/generate with correct payload', () => {
      const mockRequest = {
        prompt: 'Create an innovation presentation',
        style_filename: 'corporate_style.pptx',
        knowledge_filename: 'company_brief.pdf',
        region: 'LATAM',
        brand_id: 42,
        allow_ai_images: false,
        output_format: 'pptx',
        tier: 'standard',
      };
      const mockResponse = { job_id: 'job_abc123', status: 'pending' };

      service.generatePresentation(mockRequest).subscribe((res) => {
        expect(res).toEqual(mockResponse);
      });

      const req = httpMock.expectOne(`${API}/presentations/generate`);
      expect(req.request.method).toBe('POST');
      expect(req.request.body).toEqual(mockRequest);
      req.flush(mockResponse);
    });

    it('should POST to /presentations/generate for a PREMIUM tier request', () => {
      const premiumRequest = {
        prompt: 'Premium executive deck',
        style_filename: 'premium_style.pptx',
        knowledge_filename: 'annual_report.pdf',
        output_format: 'pdf',
        tier: 'premium',
      };
      const mockResponse = { job_id: 'job_premium_456', status: 'pending' };

      service.generatePresentation(premiumRequest).subscribe((res) => {
        expect(res.status).toBe('pending');
        expect(res.job_id).toBeDefined();
      });

      const req = httpMock.expectOne(`${API}/presentations/generate`);
      expect(req.request.body.tier).toBe('premium');
      expect(req.request.body.output_format).toBe('pdf');
      req.flush(mockResponse);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Tests de Polling de Estado del Orquestador (AgentOrchestrator States)
  // ─────────────────────────────────────────────────────────────────────────

  describe('getGenerationStatus()', () => {
    it('should GET generation status for a given jobId', () => {
      const jobId = 'job_abc123';
      const mockStatus = {
        job_id: jobId,
        status: 'processing',
        current_step: 'Agent: Redactor is writing the slides...',
        progress: 25,
      };

      service.getGenerationStatus(jobId).subscribe((res) => {
        expect(res.status).toBe('processing');
        expect(res.current_step).toContain('Redactor');
      });

      const req = httpMock.expectOne(`${API}/generation/status/${jobId}`);
      expect(req.request.method).toBe('GET');
      req.flush(mockStatus);
    });

    it('should correctly receive completed status with output_url', () => {
      const jobId = 'job_done_789';
      const completedStatus = {
        job_id: jobId,
        status: 'completed',
        current_step: 'Presentation ready for download.',
        output_url: '/outputs/job_done_789/presentation.pptx',
      };

      service.getGenerationStatus(jobId).subscribe((res) => {
        expect(res.status).toBe('completed');
        expect(res.output_url).toBeTruthy();
        expect(res.output_url).toContain('.pptx');
      });

      const req = httpMock.expectOne(`${API}/generation/status/${jobId}`);
      req.flush(completedStatus);
    });

    it('should correctly receive error status', () => {
      const jobId = 'job_error_000';
      const errorStatus = {
        job_id: jobId,
        status: 'error',
        current_step: 'Pipeline Error: LLM provider is down!',
      };

      service.getGenerationStatus(jobId).subscribe((res) => {
        expect(res.status).toBe('error');
        expect(res.current_step).toContain('Pipeline Error');
      });

      const req = httpMock.expectOne(`${API}/generation/status/${jobId}`);
      req.flush(errorStatus);
    });

    it('should correctly model all AgentOrchestrator intermediate states', () => {
      // Simula el ciclo completo de estados que el orquestador produce
      const agentStates = [
        'pending',
        'synthesizing_content',
        'content_ready',
        'planning_design',
        'design_planned',
        'qa_passed',
        'rendering',
        'completed',
      ];

      agentStates.forEach((status) => {
        service.getGenerationStatus('test_job').subscribe((res) => {
          expect(agentStates).toContain(res.status);
        });

        const req = httpMock.expectOne(`${API}/generation/status/test_job`);
        req.flush({ job_id: 'test_job', status, current_step: `Step: ${status}` });
      });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Tests de CRUD de Brands
  // ─────────────────────────────────────────────────────────────────────────

  describe('getBrands()', () => {
    it('should GET all brands from /brands', () => {
      const mockBrands = [
        { id: 1, name: 'Brand Alpha', about: 'Tech company', core_value: 'Innovation' },
        { id: 2, name: 'Brand Beta', about: 'Retail company', core_value: 'Quality' },
      ];

      service.getBrands().subscribe((brands) => {
        expect(brands.length).toBe(2);
        expect(brands[0].name).toBe('Brand Alpha');
      });

      const req = httpMock.expectOne(`${API}/brands`);
      expect(req.request.method).toBe('GET');
      req.flush(mockBrands);
    });

    it('should return an empty array when no brands exist', () => {
      service.getBrands().subscribe((brands) => {
        expect(brands).toEqual([]);
        expect(brands.length).toBe(0);
      });

      const req = httpMock.expectOne(`${API}/brands`);
      req.flush([]);
    });
  });

  describe('createBrand()', () => {
    it('should POST to /brands with FormData containing name, about, and core_value', () => {
      const mockResponse = { id: 10, name: 'New Brand', about: 'A new company', core_value: 'Trust' };

      service.createBrand('New Brand', 'A new company', 'Trust').subscribe((res) => {
        expect(res.id).toBe(10);
        expect(res.name).toBe('New Brand');
      });

      const req = httpMock.expectOne(`${API}/brands`);
      expect(req.request.method).toBe('POST');
      // Verificar que el body es FormData
      expect(req.request.body instanceof FormData).toBeTrue();
      req.flush(mockResponse);
    });
  });

  describe('updateBrand()', () => {
    it('should PUT to /brands/:id with updated FormData', () => {
      const brandId = 5;
      const mockResponse = { id: brandId, name: 'Updated Brand', about: 'Updated description' };

      service.updateBrand(brandId, 'Updated Brand', 'Updated description').subscribe((res) => {
        expect(res.id).toBe(brandId);
        expect(res.name).toBe('Updated Brand');
      });

      const req = httpMock.expectOne(`${API}/brands/${brandId}`);
      expect(req.request.method).toBe('PUT');
      req.flush(mockResponse);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Tests de Upload de Assets
  // ─────────────────────────────────────────────────────────────────────────

  describe('uploadBrandAsset()', () => {
    it('should POST to /brand/upload with correct FormData fields', () => {
      const mockFile = new File(['fake content'], 'brand_style.pptx', { type: 'application/vnd.ms-powerpoint' });
      const mockResponse = { job_key: 'upload_job_001', status: 'processing' };

      service.uploadBrandAsset(mockFile, 'style', 'exclusive', 1, 'corporate,template').subscribe((res) => {
        expect(res.status).toBe('processing');
      });

      const req = httpMock.expectOne(`${API}/brand/upload`);
      expect(req.request.method).toBe('POST');
      const formData: FormData = req.request.body;
      expect(formData.get('ingestion_type')).toBe('style');
      expect(formData.get('visibility_scope')).toBe('exclusive');
      expect(formData.get('brand_id')).toBe('1');
      expect(formData.get('manual_tags')).toBe('corporate,template');
      req.flush(mockResponse);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Tests de Catálogos (Estilos y Conocimiento)
  // ─────────────────────────────────────────────────────────────────────────

  describe('getAvailableStyles()', () => {
    it('should GET /available-styles without brandId', () => {
      const mockStyles = [{ filename: 'style_a.pptx' }, { filename: 'style_b.pptx' }];

      service.getAvailableStyles().subscribe((res) => {
        expect(res).toEqual(mockStyles);
      });

      const req = httpMock.expectOne(`${API}/available-styles`);
      expect(req.request.method).toBe('GET');
      req.flush(mockStyles);
    });

    it('should GET /available-styles?brand_id=3 when brandId is provided', () => {
      service.getAvailableStyles(3).subscribe();

      const req = httpMock.expectOne(`${API}/available-styles?brand_id=3`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });
  });

  describe('getAvailableKnowledge()', () => {
    it('should GET /available-knowledge with brandId when provided', () => {
      service.getAvailableKnowledge(7).subscribe();

      const req = httpMock.expectOne(`${API}/available-knowledge?brand_id=7`);
      expect(req.request.method).toBe('GET');
      req.flush([]);
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Tests de la Biblioteca de Assets
  // ─────────────────────────────────────────────────────────────────────────

  describe('Library methods', () => {
    it('getLibraryImages() should GET /library/images', () => {
      const mockImages = [{ id: 1, url: '/assets/img1.jpg', category: 'photos' }];
      service.getLibraryImages().subscribe((imgs) => {
        expect(imgs.length).toBe(1);
      });
      const req = httpMock.expectOne(`${API}/library/images`);
      req.flush(mockImages);
    });

    it('getLibraryImages() with brandId should GET /library/images?brand_id=5', () => {
      service.getLibraryImages(5).subscribe();
      const req = httpMock.expectOne(`${API}/library/images?brand_id=5`);
      req.flush([]);
    });

    it('getLibraryBlueprints() should GET /library/blueprints', () => {
      service.getLibraryBlueprints().subscribe();
      const req = httpMock.expectOne(`${API}/library/blueprints`);
      req.flush([]);
    });

    it('getLibraryKnowledge() should GET /library/knowledge', () => {
      service.getLibraryKnowledge().subscribe();
      const req = httpMock.expectOne(`${API}/library/knowledge`);
      req.flush([]);
    });

  });

  // ─────────────────────────────────────────────────────────────────────────
  // Tests de Gestión de Portfolios (búsqueda, paginación, rename, delete)
  // ─────────────────────────────────────────────────────────────────────────

  describe('Portfolio management', () => {
    const emptyPage = { items: [], total: 0, page: 1, page_size: 12 };

    it('getLibraryPortfolios() should GET with default pagination params', () => {
      service.getLibraryPortfolios().subscribe((res) => {
        expect(res.items).toEqual([]);
        expect(res.total).toBe(0);
      });
      const req = httpMock.expectOne(r => r.url === `${API}/library/portfolios`);
      expect(req.request.method).toBe('GET');
      expect(req.request.params.get('page')).toBe('1');
      expect(req.request.params.get('page_size')).toBe('12');
      expect(req.request.params.has('search')).toBeFalse();
      req.flush(emptyPage);
    });

    it('getLibraryPortfolios() should pass search, dates, page and brand_id as params', () => {
      service.getLibraryPortfolios(5, {
        search: 'Tesco',
        dateFrom: '2026-06-01',
        dateTo: '2026-06-11',
        page: 3,
        pageSize: 24
      }).subscribe();

      const req = httpMock.expectOne(r => r.url === `${API}/library/portfolios`);
      expect(req.request.params.get('brand_id')).toBe('5');
      expect(req.request.params.get('search')).toBe('Tesco');
      expect(req.request.params.get('date_from')).toBe('2026-06-01');
      expect(req.request.params.get('date_to')).toBe('2026-06-11');
      expect(req.request.params.get('page')).toBe('3');
      expect(req.request.params.get('page_size')).toBe('24');
      req.flush(emptyPage);
    });

    it('getLibraryPortfolios() should omit blank search', () => {
      service.getLibraryPortfolios(undefined, { search: '   ' }).subscribe();
      const req = httpMock.expectOne(r => r.url === `${API}/library/portfolios`);
      expect(req.request.params.has('search')).toBeFalse();
      req.flush(emptyPage);
    });

    it('renamePortfolio() should PATCH the display_name', () => {
      const mockResponse = { id: 42, display_name: 'Tesco Clubcard Pitch', filename: 'Presentation_42.pptx' };

      service.renamePortfolio(42, 'Tesco Clubcard Pitch').subscribe((res) => {
        expect(res.display_name).toBe('Tesco Clubcard Pitch');
      });

      const req = httpMock.expectOne(`${API}/library/portfolios/42`);
      expect(req.request.method).toBe('PATCH');
      expect(req.request.body).toEqual({ display_name: 'Tesco Clubcard Pitch' });
      req.flush(mockResponse);
    });

    it('deletePortfolio() should DELETE the presentation', () => {
      service.deletePortfolio(42).subscribe((res) => {
        expect(res.deleted).toBeTrue();
        expect(res.id).toBe(42);
      });

      const req = httpMock.expectOne(`${API}/library/portfolios/42`);
      expect(req.request.method).toBe('DELETE');
      req.flush({ deleted: true, id: 42 });
    });
  });

  // ─────────────────────────────────────────────────────────────────────────
  // Test de sanity check del servicio
  // ─────────────────────────────────────────────────────────────────────────

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
