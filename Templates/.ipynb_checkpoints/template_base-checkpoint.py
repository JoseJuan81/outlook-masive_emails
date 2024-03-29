def html_template_base(body, sign):
    return f"""
    <html
    xmlns:v="urn:schemas-microsoft-com:vml"
    xmlns:o="urn:schemas-microsoft-com:office:office"
    xmlns:w="urn:schemas-microsoft-com:office:word"
    xmlns:m="http://schemas.microsoft.com/office/2004/12/omml"
    xmlns="http://www.w3.org/TR/REC-html40"
>
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1" />
        <meta name="Generator" content="Microsoft Word 15 (filtered medium)" />
        <meta charset="utf-8" />
        <!--[if gte mso 9]>
            <xml>
                <o:shapedefaults v:ext="edit" spidmax="1027" />
            </xml>
        <![endif]-->
        <!--[if gte mso 9]>
            <xml>
                <o:shapelayout v:ext="edit">
                    <o:idmap v:ext="edit" data="1" />
                </o:shapelayout>
            </xml>
        <![endif]-->
    </head>
    <body lang="ES-PE" link="#0563C1" vlink="#954F72" style="word-wrap: break-word;">
        <div>
            
            {body}
            
            {sign}
            
        </div>
    </body>
</html>
    """