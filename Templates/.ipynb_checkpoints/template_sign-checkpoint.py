def html_template_sign(linkedin_logo, intelle, cccp, achilles):
    return f"""
        <div>
            <span lang="ES-MX" style="font-family: Nunito; color: #373d43; mso-ligatures: none; mso-fareast-language: ES-PE;">Atentamente,<o:p></o:p></span>
        </div>
        
        <div>
            <span lang="ES-MX" style="font-family: 'Nunito Black'; color: #373d43; mso-ligatures: none; mso-fareast-language: ES-PE;">Ing. José Juan Domínguez López<o:p></o:p></span>
        </div>
        
        <div>
            <span lang="ES-MX" style="font-size: 10pt; font-family: Nunito; color: #373d43; mso-ligatures: none; mso-fareast-language: ES-PE;">
                Gerente de Ventas Perú<o:p></o:p>
            </span>
            <span>&nbsp;</span>
            <span>
                <a href="https://www.linkedin.com/in/jose-juan-dom%C3%ADnguez-l%C3%B3pez/">
                    <img border="0" width="49" height="12" src='{str(linkedin_logo)}'/>
                </a>
            </span>
        </div>
        
        <div>
            <b>
                <span lang="ES-MX" style="font-size: 9pt; font-family: Nunito; color: #373d43; mso-ligatures: none; mso-fareast-language: ES-PE;">Cel: +51 970 12 70 70<o:p></o:p>
                </span>
            </b>
        </div>
        
        <div>
            <b>
                <span lang="ES-MX" style="font-size: 9pt; font-family: Nunito; color: #373d43; mso-ligatures: none; mso-fareast-language: ES-PE;">
                    <a href="https://int-ellecorporation.com/es/">https://int-ellecorporation.com/es/</a><o:p></o:p>
                </span>
            </b>
        </div>
            
        <p class="MsoNormal">
                
            <img border="0" width="184" height="57" style="width: 1.9166in; height: 0.5925in;" id="Imagen_x0020_1" src='{intelle}'/>
            <img border="0" width="140" height="46" style="width: 1.4629in; height: 0.4814in;" id="Imagen_x0020_2" src={cccp} />
            <img border="0" width="80" height="46" style="width: 0.8333in; height: 0.4814in;" id="Imagen_x0020_3" src='{str(achilles)}' /> 
                
            <b>
                <span style="font-size: 8pt; font-family: Nunito; color: #373d43; mso-ligatures: none; mso-fareast-language: ES-PE;">ID: 00089438</span>
            </b>
                <span style="font-size: 12pt; font-family: Nunito; color: #373d43; mso-ligatures: none; mso-fareast-language: ES-PE;"><o:p></o:p></span>
        </p>
            
        <p class="MsoNormal"><o:p>&nbsp;</o:p></p>
"""