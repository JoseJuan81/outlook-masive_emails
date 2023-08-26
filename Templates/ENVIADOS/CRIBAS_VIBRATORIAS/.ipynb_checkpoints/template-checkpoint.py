def html_criba_template(name, img_1, img_2, img_3, img_4, img_5):
    return f"""
    <section>
        <p class="MsoNormal">
            <span style="font-size:12pt;font-family:Nunito;color:#373d43">Hola {name},</span>
        </p>
        
        <p class="MsoNormal">
            <b>
              <span style="font-size:12pt;font-family:Nunito;color:#373d43">Int-elle</span>
            </b>
            <span style="font-size:12pt;font-family:Nunito;color:#373d43">tiene productos de alto desempeño</span>
            <span style='font-family:"Segoe UI Emoji",sans-serif'>&#128526;</span>
            <span style="font-size:12pt;font-family:Nunito;color:#373d43">
                para los paños o tamices de las cribas vibratorias que son los elementos de mayor desgaste.
            </span>
        </p>
        
        <p class="MsoNormal">
            <span style="font-size:12pt;font-family:Nunito;color:#373d43"></span>
        </p>
        <p class="MsoNormal">
            <span style="font-size:12pt;font-family:Nunito;color:#373d43">El tipo de material depende del proceso y requerimientos de cada caso sin embargo el Carburo de Cromo (CCO) y la cerámica son de los más populares.
            </span>
        </p>
        
        <p class="MsoNormal">
            <span style="font-size:12pt;font-family:Nunito;color:#373d43">¡¡ También podemos combinar los materiales</span>
            <span style='font-family:"Segoe UI Emoji",sans-serif'>&#129305;</span>
            <span style="font-size:12pt;font-family:Nunito;color:#373d43">!!, tal vez CCO para las zona de carga y cerámica para el resto</span>
            <span style='font-family:"Segoe UI Emoji",sans-serif'>&#129327;&#129327;</span>
        </p>
        
        <p class="MsoNormal">
            <span style="font-size:12pt;font-family:Nunito">El balance de cargas( abrasión – impacto ) y las características del proceso no dirá qué materiales y configuración usar.
            </span>
        </p>
      
        <p class="MsoNormal">
            <span style="font-size:12pt;font-family:Nunito;color:#373d43">
                <img width="308" height="184" src="{img_1}">
                <span>&nbsp;</span>
            </span>
            
            <span style="font-size:12pt;font-family:Nunito;color:#373d43">
                <img width="280" height="184" src="{img_2}">
                <span>&nbsp;</span>
                <img width="328" height="184" src="{img_3}">
                <span>&nbsp;</span>
                <img width="264" height="184" src="{img_4}">
                <span>&nbsp;</span>
            </span>
        </p>
        
        <p class="MsoNormal">
            <span style="font-size:12pt;font-family:Nunito;color:#373d43">
              <img width="541" height="388"src="{img_5}">
              <o:p></o:p>
            </span>
        </p>

    </section>
"""