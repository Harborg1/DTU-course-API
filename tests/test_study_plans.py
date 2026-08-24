from sqlalchemy import func, select

from app.models.study_plan import StudyPlanCourse, StudyPlanRequirement, StudyProgram
from importer.study_plan_importer import upsert_study_plan
from importer.study_plan_parser import parse_study_plan_page


SOURCE_URL = "https://student.dtu.dk/studieordninger/Bachelor/anvendt-matematik/studieplan"
MSC_SOURCE_URL = "https://www.dtu.dk/english/education/graduate/msc-programmes/applied-chemistry/curriculum"


def _row(number: str, title: str, ects: str = "5", schedule: str = "E1A") -> str:
    return (
        f'<tr><td><a href="https://kurser.dtu.dk/course/2026-2027/{number}">{number}</a></td>'
        f"<td>{title}</td><td>{ects}</td><td>point</td><td>{schedule}</td></tr>"
    )


def _table(courses: list[tuple[str, str]], alternatives: bool = False) -> str:
    rows = []
    for index, (number, title) in enumerate(courses):
        if alternatives and index:
            rows.append('<tr class="or-connecter"><td>eller</td><td></td><td></td><td></td><td></td></tr>')
        connected = ' class="connected"' if alternatives and index else ""
        rows.append(_row(number, title).replace("<tr>", f"<tr{connected}>", 1))
    return f'<table class="kursusblokclass">{"".join(rows)}</table>'


def _alternative_rows(courses: list[tuple[str, str]]) -> str:
    rows = []
    for index, (number, title) in enumerate(courses):
        if index:
            rows.append('<tr class="or-connecter"><td>or</td><td></td><td></td><td></td><td></td></tr>')
        rows.append(_row(number, title))
    return "".join(rows)


def _msc_curriculum_html() -> str:
    sustainability = [("12100", "Sustainability 1"), ("12106", "Sustainability 2"),
                      ("12105", "Sustainability 3"), ("12101", "Sustainability 4")]
    innovation = [("38402", "Innovation 1"), ("38404", "Innovation 2"), ("38400", "Innovation 3")]
    advanced = [("38403", "Advanced innovation 1"), ("38405", "Advanced innovation 2"),
                ("38401", "Advanced innovation 3")]
    innovation_two = [("26620", "Innovation course II A"), ("28311", "Innovation course II B"),
                      ("28485", "Innovation course II C")]
    core = [("26231", "Core 1"), ("26317", "Core 2"), ("26422", "Core 3"),
            ("26433", "Core 4"), ("28212", "Core 5"), ("28315", "Core 6")]
    remaining = [(f"{30000 + index}", f"Programme course {index}") for index in range(1, 39)]
    return f"""
    <html><head><title>Curriculum for Applied Chemistry</title></head><body>
    <main id="main-content"><h1>Curriculum for Applied Chemistry</h1>
    <div class="o-sdb" data-behavior="sdb">
      <h2>Programme provision</h2>
      <p>To obtain the MSc degree in Applied Chemistry the student must fulfill the following requirements:</p>
      <ul>
        <li>Have passed Polytechnical foundation courses adding up to at least 10 ECTS</li>
        <li>Have passed Programme specific courses adding up to at least 50 ECTS</li>
        <li>Have performed a Master Thesis of 30 ECTS points within the field of the general program</li>
        <li>Have passed a sufficient number of Elective courses to bring the total number of ECTS of the entire study to 120 ECTS</li>
      </ul>
      <h2>Curriculum</h2>
      <p><strong>Polytechnical foundation courses (10 ECTS)</strong></p>
      <p>The following courses are mandatory:</p>
      <table class="kursusblokclass">{_alternative_rows(sustainability)}{_alternative_rows(innovation)}</table>
      <p>Students with advanced innovation competences may take one of the following courses as an alternative to 38400/38402/38404:</p>
      {_table(advanced, alternatives=True)}
      <p><strong>Programme specific courses (50 ECTS)</strong></p>
      <p>Innovation course II - choose 5 ECTS among the following courses - if you take more than 5 ECTS in this group they will count as electives:</p>
      {_table(innovation_two)}
      <div>Core competence courses - choose 20 ECTS among the following courses:</div>
      <table class="kursusblokclass">{"".join(_row(*course) for course in core)}{_alternative_rows([("47339", "Solid state chemistry"), ("26134", "Advanced inorganic chemistry")])}</table>
      <p>The extra ECTS points in this group will automatically be a part of the overall ECTS points of the programme specific courses.</p>
      <div>Choose 25 ECTS among the rest of the programme specific courses:</div>
      {_table(remaining)}
      <p><strong>Elective courses</strong></p>
      <p>Any course classified as MSc course in DTU's course base may be an elective course. This includes programme specific courses in excess of the minimal requirements.</p>
      <p>Master students may choose as much as 10 ECTS points among the bachelor courses at DTU and courses at an equivalent level from other higher education institutions. In addition, it is possible to take MSc-level courses at other Danish universities or abroad.</p>
    </div></main></body></html>
    """


def _grouped_msc_curriculum_html() -> str:
    return f"""
    <html><head><title>Curriculum for Civil Engineering</title></head><body>
    <main id="main-content"><h1>Curriculum for Civil Engineering</h1>
    <div class="o-sdb" data-behavior="sdb">
      <h2>Programme provision</h2>
      <ul><li>Have passed Polytechnical foundation courses adding up to at least 10 ECTS points</li>
      <li>Have passed Programme-specific courses adding up to at least 50 ECTS points</li>
      <li>Have performed a Master Thesis of 30 ECTS points within the field of the general program</li>
      <li>Have passed sufficient Elective courses to bring the entire study to 120 ECTS</li></ul>
      <h2>Curriculum</h2>
      <p><strong>Polytechnical foundation courses; 10 ECTS points.</strong></p>
      <p>The following courses are mandatory:</p>
      <table class="kursusblokclass">{_alternative_rows([("12100", "Sustainability A"), ("12101", "Sustainability B")])}{_alternative_rows([("38400", "Innovation A"), ("38402", "Innovation B")])}</table>
      <p><strong>Programme-specific courses; 50 ECTS points.</strong></p>
      <p>Innovation II course options; 5 ECTS points (choose one).</p>
      {_table([("38102", "Innovation II A"), ("38106", "Innovation II B")])}
      <p>Core Competence - Narrow Choice; 15 ECTS points (choose three)</p>
      {_table([("12422", "Core A"), ("12611", "Core B"), ("12612", "Core C")])}
      <p>Programme-Specific - Wide Choice; choose 20 ECTS points (at least) from the course groups defined below. Take courses from at least two groups.</p>
      <p>Group 1: Building design.</p>{_table([("12360", "Group 1 A"), ("34844", "Group 1 B")])}
      <p>Group 2: Geotechnics.</p>{_table([("12421", "Group 2 A"), ("12431", "Group 2 B")])}
      <p><strong>Elective Courses</strong> Any MSc-level course may be an elective course. Students may choose up to 10 ECTS from BSc-level courses.</p>
    </div></main></body></html>
    """


def _semester_msc_curriculum_html() -> str:
    return f"""
    <html><head><title>Curriculum for Technology Entrepreneurship</title></head><body>
    <main id="main-content"><h1>Curriculum for Technology Entrepreneurship</h1>
    <div class="o-sdb" data-behavior="sdb">
      <h2>Programme provision</h2><ul>
      <li>Have passed 5 points in Polytechnical Foundation</li>
      <li>Have passed 55 points in the group of Programme Specific Courses</li>
      <li>Have completed an MSc Thesis equaling at least 30 points (max. 35 points)</li>
      <li>Have passed sufficient Elective Courses to bring the entire study up to 120 points</li></ul>
      <h2>Curriculum</h2>
      <p><strong>Polytechnical Foundation (mandatory course)</strong></p>
      {_table([("12100", "Sustainability A"), ("12101", "Sustainability B")], alternatives=True)}
      <h2>1st semester</h2>
      <p><strong>Programme-specific courses (mandatory courses)</strong></p>
      {_table([("38113", "Applied AI"), ("38203", "Venture project")])}
      <p>In addition to the mandatory ECTS, you should take another 10 ECTS.</p>
      <p><strong>Programme-specific courses (recommended for Specialisation: Technology)</strong></p>
      {_table([("02452", "Machine Learning"), ("42577", "Analytics")])}
      <h2>3rd semester</h2><p>For Electives you can choose any course at DTU.</p>
      <p><strong>Other DTU courses that qualify as programme-specific courses:</strong></p>
      {_table([("02805", "Social graphs")])}
      <h2>4th semester</h2><p>During the fourth semester, students develop their master's thesis.</p>
    </div></main></body></html>
    """


def _study_plan_html() -> str:
    mandatory = [
        ("01017", "Diskret matematik"),
        ("01025", "Differentialligninger"),
        ("02525", "Introduktion til Anvendt Matematik"),
        ("02526", "Matematisk modellering"),
        ("02601", "Numeriske algoritmer"),
        ("02635", "Matematisk software"),
    ]
    pool = [
        ("01018", "Diskret matematik 2"),
        ("01020", "Lineær algebra"),
        ("01125", "Topologi"),
        ("01418", "Partielle differentialligninger"),
        ("02405", "Sandsynlighedsregning"),
        ("02419", "Statistisk modellering"),
        ("02503", "Billedanalyse"),
        ("02615", "Optimering og datafitting"),
        ("42101", "Operationsanalyse"),
    ]
    return f"""
    <html><head><title>Studieplan for Anvendt Matematik (tidligere Matematik og Teknologi)</title></head>
    <body><main id="main-content">
      <h1>Studieplan for Anvendt Matematik (tidligere Matematik og Teknologi)</h1>
      <article><p>Denne studieplan gælder for <strong>studerende optaget i 2023 eller senere.</strong></p></article>
      <div class="o-sdb" data-behavior="sdb">
        <h2>Studieplan</h2>
        <div><strong>Det polytekniske grundlag</strong></div>
        <table class="kursusblokclass">
          {_row("01001", "Matematik 1a", "10")}
          {_row("02402", "Statistik")}
          <tr class="or-connecter"><td>eller</td><td></td><td></td><td></td><td></td></tr>
          {_row("02403", "Matematisk statistik").replace("<tr>", '<tr class="connected">', 1)}
        </table>
        <p><strong>Retningsspecifikke kurser</strong><br>Den studerende skal bestå 55 ECTS-point blandt de retningsspecifikke kurser.</p>
        <p>I fagblokken er følgende kurser obligatoriske.</p>
        {_table(mandatory)}
        <p>Den studerende skal tage mindst 20 ECTS-point blandt de resterende 9 retningsspecifikke kurser:</p>
        {_table(pool)}
        <p>Under valgfriheden skal følgende tre krav overholdes.</p>
        <p>Vælg mindst ét af følgende tre kurser:</p>
        {_table(pool[:3])}
        <p>Vælg mindst ét af følgende to kurser:</p>
        {_table(pool[4:6])}
        <p>Vælg mindst ét af følgende to kurser:</p>
        {_table(pool[7:9])}
        <p><strong>Projekter</strong></p>
        <table class="kursusblokclass">{_row("01666", "Fagprojekt", "10")}</table>
        <p><strong>Valgfrie kurser</strong><br>I denne fagblok skal den studerende vælge 45 point.</p>
      </div>
    </main></body></html>
    """


def test_parser_preserves_ects_pool_mandatory_courses_and_nested_choice_rules():
    data = parse_study_plan_page(_study_plan_html(), SOURCE_URL)
    directional = next(section for section in data.sections if section.name == "Retningsspecifikke kurser")

    assert data.name == "Anvendt Matematik"
    assert data.valid_from_year == 2023
    assert data.academic_year == "2026-2027"
    assert len(directional.courses) == 15
    assert sum(course.requirement_role == "mandatory" for course in directional.courses) == 6

    total = next(rule for rule in directional.requirements if rule.requirement_type == "exact_ects")
    mandatory = next(rule for rule in directional.requirements if rule.requirement_type == "all_of")
    pool = next(rule for rule in directional.requirements if rule.requirement_type == "min_ects")
    subrequirements = [rule for rule in directional.requirements if rule.requirement_type == "min_count"]
    assert float(total.required_ects) == 55
    assert mandatory.required_count == 6
    assert float(pool.required_ects) == 20
    assert len(pool.member_keys) == 9
    assert [len(rule.member_keys) for rule in subrequirements] == [3, 2, 2]
    assert all(rule.parent_key == pool.key for rule in subrequirements)
    electives = next(section for section in data.sections if section.name == "Valgfrie kurser")
    assert any(rule.requirement_type == "exact_ects" and float(rule.required_ects) == 45 for rule in electives.requirements)


def test_study_plan_is_stored_separately_and_reuses_courses_across_rules(db_session):
    data = parse_study_plan_page(_study_plan_html(), SOURCE_URL)

    assert upsert_study_plan(db_session, data) == "imported"
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(StudyProgram)) == 1
    assert db_session.scalar(select(func.count()).select_from(StudyPlanCourse)) == 19
    assert db_session.scalar(select(func.count()).select_from(StudyPlanRequirement)) == 9
    assert upsert_study_plan(db_session, data) == "unchanged"


def test_chat_explains_applied_mathematics_study_structure(client, db_session):
    data = parse_study_plan_page(_study_plan_html(), SOURCE_URL)
    upsert_study_plan(db_session, data)
    db_session.commit()

    response = client.post(
        "/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Jeg studerer Anvendt Matematik og er i tvivl om hvordan studiet er opbygget og hvilke kurser der er obligatoriske",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"] == []
    assert body["understood"]["program"] == "Anvendt Matematik"
    assert body["studyPlan"]["validFromYear"] == 2023
    directional = next(
        section for section in body["studyPlan"]["sections"] if section["name"] == "Retningsspecifikke kurser"
    )
    assert sum(course["requirementRole"] == "mandatory" for course in directional["courses"]) == 6
    assert any(rule["requiredEcts"] == 55 for rule in directional["requirements"])
    assert any(rule["requiredEcts"] == 20 and len(rule["courses"]) == 9 for rule in directional["requirements"])
    assert sum(rule["isSubrequirement"] for rule in directional["requirements"]) == 3
    assert "tælles ikke dobbelt" in body["reply"]


def test_chat_uses_degree_context_to_resolve_bilingual_program_names(client, db_session):
    bachelor = parse_study_plan_page(
        _study_plan_html().replace("Anvendt Matematik", "Bioteknologi"),
        "https://student.dtu.dk/studieordninger/Bachelor/bioteknologi/studieplan",
    )
    master = parse_study_plan_page(
        _msc_curriculum_html().replace("Applied Chemistry", "Biotechnology"),
        "https://www.dtu.dk/english/education/graduate/msc-programmes/biotechnology/curriculum",
    )
    upsert_study_plan(db_session, bachelor)
    upsert_study_plan(db_session, master)
    db_session.commit()

    master_response = client.post(
        "/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Jeg læser bioteknologi på kandidaten. Hvad er reglerne for mit studie?",
                }
            ]
        },
    )
    bachelor_response = client.post(
        "/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "I study Biotechnology on my bachelor's. What are my degree requirements?",
                }
            ]
        },
    )

    assert master_response.status_code == 200
    assert master_response.json()["understood"] == {
        "topic": "study plan",
        "level": "Master",
        "ects": None,
        "language": None,
        "period": None,
        "program": "Biotechnology",
    }
    assert bachelor_response.status_code == 200
    assert bachelor_response.json()["understood"]["program"] == "Bioteknologi"
    assert bachelor_response.json()["understood"]["level"] == "Bachelor"


def test_chat_answers_general_msc_ects_without_program_name(client):
    response = client.post(
        "/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "Hvor mange ECTS skal man have for at gennemføre en kandidat på DTU?",
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["reply"].startswith("En ordinær toårig kandidatuddannelse (MSc) på DTU er på 120 ECTS.")
    assert "kandidatspeciale på 30 ECTS" in body["reply"]
    assert body["understood"]["topic"] == "MSc degree requirements"
    assert body["understood"]["level"] == "Master"
    assert body["understood"]["ects"] == 120
    assert body["isDirectAnswer"] is True


def test_chat_remembers_program_context_and_tolerates_a_spelling_error(client, db_session):
    curriculum_html = (
        _msc_curriculum_html()
        .replace("Applied Chemistry", "Computer Science and Engineering")
        .replace(
            "Choose 25 ECTS among the rest of the programme specific courses:",
            "The remaining ECTS points in the programme specific block must be chosen "
            "from the following list of courses:",
        )
    )
    program = parse_study_plan_page(
        curriculum_html,
        "https://www.dtu.dk/english/education/graduate/msc-programmes/computer-science-and-engineering/curriculum",
    )
    upsert_study_plan(db_session, program)
    db_session.commit()

    contextual_response = client.post(
        "/api/chat",
        json={
            "messages": [
                {"role": "user", "content": "Jeg læser datalogi på kandidaten."},
                {
                    "role": "user",
                    "content": "Hvordan er min uddannelse bygget op, og hvilke kurser skal jeg tage?",
                },
            ]
        },
    )
    typo_response = client.post(
        "/api/chat",
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "I study Computer Sciense and Engineering. Which courses do I need?",
                }
            ]
        },
    )

    assert contextual_response.status_code == 200
    contextual_body = contextual_response.json()
    assert contextual_body["understood"]["program"] == "Computer Science and Engineering"
    assert contextual_body["understood"]["level"] == "Master"
    assert "Vælg ét kursus på 5 ECTS blandt: 12100" in contextual_body["reply"]
    assert "The following courses are mandatory — 12100" not in contextual_body["reply"]
    assert "den brede pulje med" in contextual_body["reply"]
    assert "following list of courses: Elective courses" not in contextual_body["reply"]
    elective_rule = "Any course classified as MSc course in DTU's course base may be an elective course."
    assert contextual_body["reply"].count(elective_rule) == 1
    assert typo_response.status_code == 200
    assert typo_response.json()["understood"]["program"] == "Computer Science and Engineering"


def test_parser_supports_english_h2_sections_and_programme_specific_rules():
    html = f"""
    <html><head><title>Study plan 2025 - General Engineering</title></head><body>
    <main id="main-content"><h1>Study plan 2025 - General Engineering</h1>
    <div class="o-sdb" data-behavior="sdb">
      <h2>Curriculum</h2>
      <h2>Polytechnical Foundation</h2>
      {_table([("01003", "Mathematics 1a")])}
      <h2>Programme Specific Courses</h2>
      <p>Mandatory for all:</p>{_table([("01034", "Advanced Engineering Mathematics")])}
      <p>It is mandatory to choose two of the following four courses:</p>
      {_table([("02135", "Intro 1"), ("02501", "Intro 2"), ("10022", "Intro 3"), ("12111", "Intro 4")])}
      <h2>Living Systems - Programme Specific Courses</h2>
      <p>Mandatory:</p>{_table([("25106", "Introduction to Living Systems")])}
      <p>Choose 20 ECTS among the courses below:</p>{_table([("22111", "Bioinformatics"), ("27022", "Biology")])}
      <h2>Electives</h2>
      <p>Students must choose 35-40 ECTS points from available BSc level courses.</p>
      <p>Bachelor's students may have up to 10 ECTS credits at BEng level.</p>
      <h2>MSc-courses that are pre-approved as elective courses for BSc in General Engineering</h2>
      {_table([("01325", "Mathematics 4")])}
    </div></main></body></html>
    """
    data = parse_study_plan_page(
        html,
        "https://student.dtu.dk/en/programme-specifications/Bachelor-of-science-in-engineering/General-Engineering/current-study-plan",
    )

    assert data.name == "General Engineering"
    assert data.slug == "general-engineering"
    assert data.degree_type == "Bachelor"
    programme = next(section for section in data.sections if section.name == "Programme Specific Courses")
    assert [rule.requirement_type for rule in programme.requirements] == ["all_of", "min_count"]
    assert programme.requirements[1].required_count == 2
    living = next(section for section in data.sections if section.name.startswith("Living Systems"))
    assert any(rule.requirement_type == "min_ects" and float(rule.required_ects) == 20 for rule in living.requirements)
    electives = next(section for section in data.sections if section.name == "Electives")
    assert [rule.requirement_type for rule in electives.requirements] == ["ects_range", "max_ects"]
    preapproved = data.sections[-1]
    assert preapproved.courses[0].requirement_role == "preapproved"


def test_parser_supports_h2_pool_rules_ranges_and_external_course_numbers():
    html = f"""
    <html><head><title>Studieplan for Medicin og Teknologi</title></head><body>
    <main id="main-content"><h1>Studieplan for Medicin og Teknologi</h1>
    <p>Gælder for studerende optaget i 2023 eller senere.</p>
    <div class="o-sdb" data-behavior="sdb">
      <h2>Studieplan</h2><h2>Det polytekniske grundlag</h2>{_table([("01001", "Matematik 1a")])}
      <h2>Retningsspecifikke kurser</h2>
      <p><em>Pulje 1. Obligatoriske retningsspecifikke KU-kurser</em></p>
      <table class="kursusblokclass">{_row("KU002", "Basal humanbiologi")}</table>
      <p><em>Pulje 3. Semi-obligatoriske retningsspecifikke kurser på KU SUND.</em></p>
      <p>Den studerende skal bestå 7,5 - 10 ECTS fra denne pulje.</p>
      <table class="kursusblokclass">{_row("KU010", "Anatomi", "7,5")}{_row("KU012", "Immunologi", "7,5")}</table>
      <h2>Valgfrie kurser</h2><p>I denne fagblok skal den studerende bestå kurser svarende til 45 ECTS.</p>
      <ul><li>Civilbachelorstuderende må have op til 10 ECTS på diplomingeniørniveau.</li></ul>
    </div></main></body></html>
    """
    data = parse_study_plan_page(
        html,
        "https://student.dtu.dk/studieordninger/Bachelor/medicin-og-teknologi/studieplan",
    )

    directional = next(section for section in data.sections if section.name == "Retningsspecifikke kurser")
    assert directional.courses[0].course_number == "KU002"
    assert directional.courses[0].requirement_role == "mandatory"
    assert [course.requirement_role for course in directional.courses[1:]] == ["choice", "choice"]
    range_rule = next(rule for rule in directional.requirements if rule.requirement_type == "ects_range")
    assert float(range_rule.required_ects) == 7.5
    assert len(range_rule.member_keys) == 2
    electives = next(section for section in data.sections if section.name == "Valgfrie kurser")
    assert {rule.requirement_type for rule in electives.requirements} == {"exact_ects", "max_ects"}


def test_parser_preserves_msc_provision_course_pools_and_elective_rules(db_session):
    data = parse_study_plan_page(_msc_curriculum_html(), MSC_SOURCE_URL)

    assert data.name == "Applied Chemistry"
    assert data.slug == "applied-chemistry"
    assert data.degree_type == "Master"
    assert data.academic_year == "2026-2027"
    assert [section.name for section in data.sections] == [
        "Programme provision",
        "Polytechnical foundation courses",
        "Programme specific courses",
        "Elective courses",
    ]

    provision = data.sections[0]
    assert [(rule.requirement_type, float(rule.required_ects)) for rule in provision.requirements] == [
        ("min_ects", 10),
        ("min_ects", 50),
        ("exact_ects", 30),
        ("total_ects", 120),
    ]

    foundation = data.sections[1]
    assert len(foundation.courses) == 10
    assert [len(rule.member_keys) for rule in foundation.requirements] == [4, 6]
    assert all(rule.requirement_type == "one_of" and rule.required_count == 1 for rule in foundation.requirements)
    assert {"38403", "38405", "38401"}.issubset(foundation.requirements[1].member_keys)
    assert "advanced innovation competences" in foundation.requirements[1].description

    programme = data.sections[2]
    assert len(programme.courses) == 49
    pools = [rule for rule in programme.requirements if rule.requirement_type == "group_ects"]
    assert [float(rule.required_ects) for rule in pools] == [5, 20, 25]
    assert [len(rule.member_keys) for rule in pools] == [3, 8, 38]
    alternative = next(rule for rule in programme.requirements if rule.requirement_type == "conditional_one_of")
    assert alternative.parent_key == pools[1].key
    assert set(alternative.member_keys) == {"47339", "26134"}
    assert any(rule.requirement_type == "excess_counts" for rule in programme.requirements)

    electives = data.sections[3]
    assert [rule.requirement_type for rule in electives.requirements] == ["eligibility", "max_ects"]
    assert float(electives.requirements[1].required_ects) == 10

    assert upsert_study_plan(db_session, data) == "imported"
    db_session.commit()
    assert db_session.scalar(select(func.count()).select_from(StudyPlanCourse)) == 59
    assert db_session.scalar(select(func.count()).select_from(StudyPlanRequirement)) == 13


def test_msc_parser_preserves_grouped_pools_and_combined_elective_heading():
    data = parse_study_plan_page(
        _grouped_msc_curriculum_html(),
        "https://www.dtu.dk/english/education/graduate/msc-programmes/civil-engineering/curriculum",
    )

    programme = next(section for section in data.sections if section.name == "Programme specific courses")
    assert any(rule.requirement_type == "one_of" and len(rule.member_keys) == 2 for rule in programme.requirements)
    assert any(
        rule.requirement_type == "exact_count" and rule.required_count == 3 and len(rule.member_keys) == 3
        for rule in programme.requirements
    )
    wide_pool = next(rule for rule in programme.requirements if rule.requirement_type == "min_ects")
    assert float(wide_pool.required_ects) == 20
    assert len(wide_pool.member_keys) == 4
    assert any(
        rule.requirement_type == "min_groups" and rule.required_count == 2 and rule.parent_key == wide_pool.key
        for rule in programme.requirements
    )
    assert sum(rule.requirement_type == "course_group" for rule in programme.requirements) == 2

    electives = next(section for section in data.sections if section.name == "Elective courses")
    assert {rule.requirement_type for rule in electives.requirements} == {"eligibility", "max_ects"}


def test_msc_parser_preserves_points_thesis_range_and_semester_structure():
    data = parse_study_plan_page(
        _semester_msc_curriculum_html(),
        "https://www.dtu.dk/english/education/graduate/msc-programmes/technology-entrepreneurship/curriculum",
    )

    provision = data.sections[0]
    assert [(rule.requirement_type, float(rule.required_ects)) for rule in provision.requirements] == [
        ("exact_ects", 5),
        ("exact_ects", 55),
        ("ects_range", 30),
        ("total_ects", 120),
    ]
    first = next(section for section in data.sections if section.name == "1st semester")
    assert sum(course.requirement_role == "mandatory" for course in first.courses) == 2
    assert sum(course.requirement_role == "recommended" for course in first.courses) == 2
    assert any(
        rule.requirement_type == "additional_ects" and float(rule.required_ects) == 10
        for rule in first.requirements
    )
    third = next(section for section in data.sections if section.name == "3rd semester")
    assert {rule.requirement_type for rule in third.requirements} == {"eligibility", "eligible_pool"}
