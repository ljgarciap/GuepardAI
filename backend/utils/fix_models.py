import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

content = open('/app/models.py', 'r', encoding='utf-8').read()
idx = content.find('job = relationship("GenerationJob", back_populates="slides")')
if idx != -1:
    idx += len('job = relationship("GenerationJob", back_populates="slides")')
    correct_content = content[:idx] + '''

class ArtDirectorDecision(Base):
    """
    BITÁCORA DE DECISIONES (v34.0).
    Records the 'porqué' de cada visual choice.
    """
    __tablename__ = "art_director_decisions"

    id           = Column(Integer, primary_key=True, index=True)
    job_id       = Column(Integer, ForeignKey("generation_jobs.id"))
    slide_number = Column(Integer)
    
    decision_type = Column(String(50)) # 'layout', 'asset_selection', 'color_logic'
    summary       = Column(Text)
    reasoning     = Column(Text)
    
    # Bitácora de Auditoría (v4.0)
    prompt_used  = Column(Text, nullable=True)
    response_raw = Column(Text, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    
    created_at   = Column(DateTime, default=datetime.datetime.utcnow)

    job = relationship("GenerationJob")

class SystemConfig(Base):
    """
    TABLA PARAMÉTRICA (v18.1).
    Evita el hardcodeo de modelos y límites del sistema.
    """
    __tablename__ = "system_configs"

    id    = Column(Integer, primary_key=True, index=True)
    key   = Column(String(100), unique=True, index=True, nullable=False)
    value = Column(Text, nullable=False)
    description = Column(String(255), nullable=True)
    updated_at  = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
'''
    with open('/app/models.py', 'w', encoding='utf-8') as f:
        f.write(correct_content)
    print('Fixed models.py')
else:
    print('Anchor not found')

# Also run DB migration
from database import engine
from sqlalchemy import text
with engine.begin() as conn:
    conn.execute(text('ALTER TABLE art_director_decisions ALTER COLUMN summary TYPE TEXT;'))
print('DB Migration successful')
